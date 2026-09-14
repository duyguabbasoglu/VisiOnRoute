# Staging: ucuz profil. Uygulamadan önce backend bucket/tablosunu oluşturun
# (bkz. docs/operations/deployment.md) ve aşağıdaki backend bloğunu doldurun.

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
  #   key            = "staging/terraform.tfstate"
  #   region         = "eu-central-1"
  #   dynamodb_table = "visionroute-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = "eu-central-1"
}

variable "certificate_arn" {
  description = "Staging ALB'si için ACM sertifikası (üretim benzeri ortam HTTPS gerektirir)."
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

  environment            = "staging"
  db_instance_class      = "db.t4g.micro"
  db_multi_az            = false
  db_deletion_protection = false
  redis_node_type        = "cache.t4g.micro"
  api_desired_count      = 1
  worker_desired_count   = 1
  monthly_budget_usd     = 100
  certificate_arn        = var.certificate_arn
  budget_alert_email     = var.budget_alert_email
  app_domain             = var.app_domain
  smtp_host              = var.smtp_host
  smtp_from              = var.smtp_from
  smtp_username          = var.smtp_username
  github_repository      = var.github_repository
}

output "alb_dns_name" {
  value = module.stack.alb_dns_name
}

output "app_secrets_arn" {
  value = module.stack.app_secrets_arn
}
