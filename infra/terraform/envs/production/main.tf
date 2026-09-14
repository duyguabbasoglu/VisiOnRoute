# Production: multi-AZ veritabanı, silme koruması, daha büyük profiller.
# Üretim değişiklikleri CI'da onay kapısından geçer (cd.yml).

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
  # backend "s3" {
  #   bucket         = "visionroute-terraform-state"
  #   key            = "production/terraform.tfstate"
  #   region         = "eu-central-1"
  #   dynamodb_table = "visionroute-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = "eu-central-1"
}

variable "certificate_arn" {
  description = "Üretim ALB'si için zorunlu ACM sertifikası."
  type        = string
}

variable "budget_alert_email" {
  type    = string
  default = ""
}

variable "app_domain" {
  description = "Uygulama alan adı (ör. filo.ornek.com.tr)."
  type        = string
}

variable "smtp_host" {
  type = string
}

variable "smtp_from" {
  type = string
}

variable "smtp_username" {
  type    = string
  default = ""
}

variable "github_repository" {
  type    = string
  default = ""
}

module "stack" {
  source = "../../modules/stack"

  environment             = "production"
  db_instance_class       = "db.m7g.large"
  db_multi_az             = true
  db_deletion_protection  = true
  db_allocated_storage_gb = 100
  redis_node_type         = "cache.t4g.small"
  api_desired_count       = 2
  worker_desired_count    = 2
  api_cpu                 = 512
  api_memory              = 1024
  certificate_arn         = var.certificate_arn
  monthly_budget_usd      = 1000
  budget_alert_email      = var.budget_alert_email
  app_domain              = var.app_domain
  smtp_host               = var.smtp_host
  smtp_from               = var.smtp_from
  smtp_username           = var.smtp_username
  github_repository       = var.github_repository
}

output "alb_dns_name" {
  value = module.stack.alb_dns_name
}

output "app_secrets_arn" {
  value = module.stack.app_secrets_arn
}
