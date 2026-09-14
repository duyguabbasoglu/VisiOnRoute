output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "database_endpoint" {
  value     = aws_db_instance.main.address
  sensitive = true
}

output "evidence_bucket" {
  value = aws_s3_bucket.evidence.bucket
}

output "ecr_api_url" {
  value = aws_ecr_repository.api.repository_url
}

output "ecr_web_url" {
  value = aws_ecr_repository.web.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "jwt_keys_secret_arn" {
  value = aws_secretsmanager_secret.jwt_keys.arn
}

output "app_secrets_arn" {
  description = "Uygulama sırları (field_encryption_keys, smtp_password, metrics_token) için JSON secret."
  value       = aws_secretsmanager_secret.app.arn
}

output "github_deploy_role_arn" {
  value = var.github_repository == "" ? null : aws_iam_role.github_deploy[0].arn
}

output "app_url" {
  value = local.app_url
}
