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
