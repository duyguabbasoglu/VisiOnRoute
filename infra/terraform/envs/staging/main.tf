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
  # certificate_arn      = "arn:aws:acm:..."   # ACM sertifikası hazır olunca
  # budget_alert_email   = "ops@ornek.example"
}

output "alb_dns_name" {
  value = module.stack.alb_dns_name
}
