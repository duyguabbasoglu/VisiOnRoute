# VisiOnRoute AWS stack: VPC, RDS(+PostGIS), Redis, S3, ECR, ECS Fargate, ALB.
# Security posture: no public database, private subnets for services, least
# privilege task roles, encryption at rest (KMS) and in transit.

terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

locals {
  name = "visionroute-${var.environment}"
  tags = merge(
    {
      Project     = "visionroute"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags,
  )
  azs = ["${var.aws_region}a", "${var.aws_region}b"]
}

# ---------------------------------------------------------------- network

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = local.name })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = local.tags
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, count.index)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = merge(local.tags, { Name = "${local.name}-public-${count.index}" })
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 8)
  availability_zone = local.azs[count.index]
  tags              = merge(local.tags, { Name = "${local.name}-private-${count.index}" })
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = local.tags
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = local.tags
  depends_on    = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = local.tags
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
  tags = local.tags
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ---------------------------------------------------------------- security groups

resource "aws_security_group" "alb" {
  name_prefix = "${local.name}-alb-"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.tags
}

resource "aws_security_group" "service" {
  name_prefix = "${local.name}-svc-"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  ingress {
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = local.tags
}

resource "aws_security_group" "database" {
  name_prefix = "${local.name}-db-"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.service.id]
  }
  tags = local.tags
}

resource "aws_security_group" "redis" {
  name_prefix = "${local.name}-redis-"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.service.id]
  }
  tags = local.tags
}

# ---------------------------------------------------------------- kms & secrets

resource "aws_kms_key" "main" {
  description             = "${local.name} encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  tags                    = local.tags
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "db_password" {
  name_prefix = "${local.name}-db-password-"
  kms_key_id  = aws_kms_key.main.arn
  tags        = local.tags
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}

# JWT anahtar çifti dağıtım hattında üretilir ve bu secrete yazılır;
# Terraform yalnızca kabı oluşturur (anahtar üretimi state'e sızmasın diye).
resource "aws_secretsmanager_secret" "jwt_keys" {
  name_prefix = "${local.name}-jwt-keys-"
  kms_key_id  = aws_kms_key.main.arn
  tags        = local.tags
}

# Uygulama sırları tek JSON secret'ında (değerleri dağıtım hattı/operatör
# yazar, Terraform state'ine girmez). Anahtarlar:
#   field_encryption_keys  {"k1": "<Fernet anahtarı>"} biçiminde JSON metni
#   smtp_password          SMTP parolası (yoksa "")
#   metrics_token          /metrics Bearer anahtarı, en az 32 karakter (yoksa "")
resource "aws_secretsmanager_secret" "app" {
  name_prefix = "${local.name}-app-secrets-"
  kms_key_id  = aws_kms_key.main.arn
  tags        = local.tags
}

# ---------------------------------------------------------------- database

resource "aws_db_subnet_group" "main" {
  name_prefix = local.name
  subnet_ids  = aws_subnet.private[*].id
  tags        = local.tags
}

resource "aws_db_instance" "main" {
  identifier_prefix          = "${local.name}-"
  engine                     = "postgres"
  engine_version             = "17"
  instance_class             = var.db_instance_class
  allocated_storage          = var.db_allocated_storage_gb
  db_name                    = "visionroute"
  username                   = "visionroute"
  password                   = random_password.db.result
  db_subnet_group_name       = aws_db_subnet_group.main.name
  vpc_security_group_ids     = [aws_security_group.database.id]
  multi_az                   = var.db_multi_az
  publicly_accessible        = false
  storage_encrypted          = true
  kms_key_id                 = aws_kms_key.main.arn
  backup_retention_period    = 14
  deletion_protection        = var.db_deletion_protection
  skip_final_snapshot        = var.environment != "production"
  final_snapshot_identifier  = var.environment == "production" ? "${local.name}-final" : null
  copy_tags_to_snapshot      = true
  auto_minor_version_upgrade = true
  tags                       = local.tags
}

# ---------------------------------------------------------------- redis

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_cluster" "main" {
  cluster_id         = "${local.name}-redis"
  engine             = "redis"
  node_type          = var.redis_node_type
  num_cache_nodes    = 1
  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]
  tags               = local.tags
}

# ---------------------------------------------------------------- storage

resource "aws_s3_bucket" "evidence" {
  bucket_prefix = "${local.name}-evidence-"
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket                  = aws_s3_bucket.evidence.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
  }
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    id     = "retention"
    status = "Enabled"
    filter {}
    # Silinen/üzerine yazılan nesneler (KVKK silme, saklama temizliği) en fazla
    # 7 gün eski sürüm olarak kalır; kazara silmeye karşı kısa kurtarma penceresi.
    noncurrent_version_expiration {
      noncurrent_days = 7
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "evidence_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.evidence.arn,
      "${aws_s3_bucket.evidence.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "evidence" {
  bucket     = aws_s3_bucket.evidence.id
  policy     = data.aws_iam_policy_document.evidence_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.evidence]
}

# Tarayıcı, imzalı POST ile kanıt dosyasını doğrudan bucket'a yükler.
resource "aws_s3_bucket_cors_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  cors_rule {
    allowed_methods = ["POST"]
    allowed_origins = [local.app_url]
    allowed_headers = ["*"]
    max_age_seconds = 600
  }
}

# ---------------------------------------------------------------- ecr

resource "aws_ecr_repository" "api" {
  name                 = "${local.name}/api"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = local.tags
}

resource "aws_ecr_repository" "web" {
  name                 = "${local.name}/web"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = local.tags
}

# ---------------------------------------------------------------- iam

data "aws_iam_policy_document" "task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name_prefix        = "${local.name}-exec-"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_secretsmanager_secret.db_password.arn,
      aws_secretsmanager_secret.jwt_keys.arn,
      aws_secretsmanager_secret.app.arn,
    ]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.main.arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name_prefix = "secrets-"
  role        = aws_iam_role.execution.id
  policy      = data.aws_iam_policy_document.execution_secrets.json
}

# API görev rolü: yalnızca kanıt bucket'ına erişim (least privilege).
resource "aws_iam_role" "api_task" {
  name_prefix        = "${local.name}-api-"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "api_s3" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.evidence.arn}/*"]
  }
  # HEAD on a missing key returns 404 (not 403) only with ListBucket; prefix
  # deletion (KVKK) lists objects.
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.evidence.arn]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.main.arn]
  }
}

resource "aws_iam_role_policy" "api_s3" {
  name_prefix = "s3-"
  role        = aws_iam_role.api_task.id
  policy      = data.aws_iam_policy_document.api_s3.json
}

# ---------------------------------------------------------------- logs

resource "aws_cloudwatch_log_group" "services" {
  for_each          = toset(["api", "web", "worker", "scheduler"])
  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = 90
  kms_key_id        = null # CloudWatch varsayılan şifrelemesi; KMS entegrasyonu opsiyonel
  tags              = local.tags
}

# ---------------------------------------------------------------- alb

resource "aws_lb" "main" {
  name_prefix                = "vr-"
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = aws_subnet.public[*].id
  drop_invalid_header_fields = true
  # Live-operation streams send a keepalive every 15 s.
  idle_timeout = 60
  tags         = local.tags
}

resource "aws_lb_target_group" "api" {
  name_prefix = "vrapi-"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"
  health_check {
    path                = "/health/ready"
    healthy_threshold   = 2
    unhealthy_threshold = 5
    interval            = 15
  }
  tags = local.tags
}

resource "aws_lb_target_group" "web" {
  name_prefix = "vrweb-"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"
  health_check {
    path                = "/giris"
    healthy_threshold   = 2
    unhealthy_threshold = 5
    interval            = 30
  }
  tags = local.tags
}

resource "aws_lb_listener" "https" {
  count             = var.certificate_arn == "" ? 0 : 1
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener_rule" "api" {
  count        = var.certificate_arn == "" ? 0 : 1
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  condition {
    path_pattern {
      values = ["/api/*", "/health/*"]
    }
  }
}

# HTTP: sertifika varsa HTTPS'e yönlendir; yoksa (yalnızca staging) doğrudan sun.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [] : [1]
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.web.arn
    }
  }
}

resource "aws_lb_listener_rule" "api_http" {
  count        = var.certificate_arn == "" ? 1 : 0
  listener_arn = aws_lb_listener.http.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  condition {
    path_pattern {
      values = ["/api/*", "/health/*"]
    }
  }
}

# ---------------------------------------------------------------- ecs

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = local.tags
}

locals {
  app_url = "https://${var.app_domain}"

  # API, worker ve scheduler aynı imajı ve yapılandırmayı paylaşır.
  app_environment = [
    { name = "VISIONROUTE_ENVIRONMENT", value = var.environment },
    { name = "VISIONROUTE_DATABASE_HOST", value = aws_db_instance.main.address },
    { name = "VISIONROUTE_DATABASE_PORT", value = tostring(aws_db_instance.main.port) },
    { name = "VISIONROUTE_DATABASE_NAME", value = aws_db_instance.main.db_name },
    { name = "VISIONROUTE_DATABASE_USER", value = aws_db_instance.main.username },
    { name = "VISIONROUTE_DATABASE_SSL", value = "true" },
    { name = "VISIONROUTE_REDIS_URL", value = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:6379/0" },
    { name = "VISIONROUTE_RATE_LIMIT_BACKEND", value = "redis" },
    { name = "VISIONROUTE_COOKIE_SECURE", value = "true" },
    { name = "VISIONROUTE_PUBLIC_APP_URL", value = local.app_url },
    { name = "VISIONROUTE_PUBLIC_API_URL", value = local.app_url },
    { name = "VISIONROUTE_CORS_ORIGINS", value = jsonencode([local.app_url]) },
    { name = "VISIONROUTE_STORAGE_BACKEND", value = "s3" },
    { name = "VISIONROUTE_S3_BUCKET_EVIDENCE", value = aws_s3_bucket.evidence.bucket },
    { name = "VISIONROUTE_S3_REGION", value = var.aws_region },
    { name = "VISIONROUTE_MAIL_BACKEND", value = "smtp" },
    { name = "VISIONROUTE_SMTP_HOST", value = var.smtp_host },
    { name = "VISIONROUTE_SMTP_PORT", value = tostring(var.smtp_port) },
    { name = "VISIONROUTE_SMTP_FROM", value = var.smtp_from },
    { name = "VISIONROUTE_SMTP_USERNAME", value = var.smtp_username },
    { name = "VISIONROUTE_SMTP_STARTTLS", value = "true" },
    { name = "VISIONROUTE_FIELD_ENCRYPTION_PRIMARY_KEY_ID", value = var.field_encryption_primary_key_id },
    # Görevler yalnızca ALB güvenlik grubundan erişilebilir; X-Forwarded-For'a güvenilir.
    { name = "FORWARDED_ALLOW_IPS", value = "*" },
  ]

  app_secrets = [
    { name = "VISIONROUTE_DATABASE_PASSWORD", valueFrom = aws_secretsmanager_secret.db_password.arn },
    { name = "VISIONROUTE_JWT_PRIVATE_KEY", valueFrom = "${aws_secretsmanager_secret.jwt_keys.arn}:private::" },
    { name = "VISIONROUTE_JWT_PUBLIC_KEY", valueFrom = "${aws_secretsmanager_secret.jwt_keys.arn}:public::" },
    { name = "VISIONROUTE_FIELD_ENCRYPTION_KEYS", valueFrom = "${aws_secretsmanager_secret.app.arn}:field_encryption_keys::" },
    { name = "VISIONROUTE_SMTP_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:smtp_password::" },
    { name = "VISIONROUTE_METRICS_TOKEN", valueFrom = "${aws_secretsmanager_secret.app.arn}:metrics_token::" },
  ]

  backend_processes = {
    worker    = { command = ["visionroute", "worker", "run"], desired_count = var.worker_desired_count }
    scheduler = { command = ["visionroute", "scheduler", "run"], desired_count = var.scheduler_desired_count }
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api_task.arn
  container_definitions = jsonencode([
    {
      name         = "api"
      image        = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
      essential    = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment  = local.app_environment
      secrets      = local.app_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.services["api"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])
  tags = local.tags
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.service.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  depends_on = [aws_lb_listener.http]
  tags       = local.tags
}

# Worker ve scheduler: aynı imaj, farklı komut. Scheduler tek replika çalışır
# (ek replikalar advisory lock nedeniyle boşta kalır).
resource "aws_ecs_task_definition" "backend" {
  for_each                 = local.backend_processes
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.api_task.arn
  container_definitions = jsonencode([
    {
      name        = each.key
      image       = "${aws_ecr_repository.api.repository_url}:${var.image_tag}"
      essential   = true
      command     = each.value.command
      environment = local.app_environment
      secrets     = local.app_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.services[each.key].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = each.key
        }
      }
    }
  ])
  tags = local.tags
}

resource "aws_ecs_service" "backend" {
  for_each        = local.backend_processes
  name            = each.key
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend[each.key].arn
  desired_count   = each.value.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.service.id]
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  tags = local.tags
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${local.name}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  # No task role: the web server makes no AWS API calls.
  container_definitions = jsonencode([
    {
      name         = "web"
      image        = "${aws_ecr_repository.web.repository_url}:${var.image_tag}"
      essential    = true
      portMappings = [{ containerPort = 3000, protocol = "tcp" }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.services["web"].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "web"
        }
      }
    }
  ])
  tags = local.tags
}

resource "aws_ecs_service" "web" {
  name            = "web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.web_desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.service.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  depends_on = [aws_lb_listener.http]
  tags       = local.tags
}

# ---------------------------------------------------------------- ci/cd (optional)

# GitHub Actions OIDC: uzun ömürlü AWS anahtarı olmadan imaj itme ve migration
# görevi çalıştırma. Terraform plan/apply ayrıca durum bucket'ına ve yönetilen
# kaynaklara erişim gerektirir; bu yetki bu role bilinçli olarak VERİLMEZ
# (bkz. docs/operations/deployment.md).
resource "aws_iam_openid_connect_provider" "github" {
  count           = var.github_repository == "" ? 0 : 1
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
  tags            = local.tags
}

data "aws_iam_policy_document" "github_assume" {
  count = var.github_repository == "" ? 0 : 1
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github[0].arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.environment}"]
    }
  }
}

data "aws_iam_policy_document" "github_deploy" {
  count = var.github_repository == "" ? 0 : 1
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
      "ecr:BatchGetImage",
    ]
    resources = [aws_ecr_repository.api.arn, aws_ecr_repository.web.arn]
  }
  statement {
    actions   = ["ecs:RunTask", "ecs:DescribeTasks", "ecs:DescribeServices", "ecs:DescribeTaskDefinition"]
    resources = ["*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.main.arn]
    }
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.api_task.arn]
  }
}

resource "aws_iam_role" "github_deploy" {
  count              = var.github_repository == "" ? 0 : 1
  name_prefix        = "${local.name}-gh-"
  assume_role_policy = data.aws_iam_policy_document.github_assume[0].json
  tags               = local.tags
}

resource "aws_iam_role_policy" "github_deploy" {
  count  = var.github_repository == "" ? 0 : 1
  role   = aws_iam_role.github_deploy[0].id
  policy = data.aws_iam_policy_document.github_deploy[0].json
}

# ---------------------------------------------------------------- budget

resource "aws_budgets_budget" "monthly" {
  count        = var.budget_alert_email == "" ? 0 : 1
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
