variable "environment" {
  description = "Ortam adı (staging | production)."
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment staging veya production olmalıdır."
  }
}

variable "aws_region" {
  description = "AWS bölgesi (KVKK veri yerleşimi için eu-central-1 varsayılan)."
  type        = string
  default     = "eu-central-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "db_instance_class" {
  description = "RDS örnek sınıfı (staging için ucuz profil)."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "worker_desired_count" {
  type    = number
  default = 1
}

variable "api_cpu" {
  type    = number
  default = 256
}

variable "api_memory" {
  type    = number
  default = 512
}

variable "certificate_arn" {
  description = "ALB HTTPS dinleyicisi için ACM sertifika ARN'i. Boşsa yalnızca HTTP (yalnızca staging'de kabul edilebilir)."
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "Dağıtılacak konteyner imaj etiketi."
  type        = string
  default     = "latest"
}

variable "monthly_budget_usd" {
  description = "Bütçe alarmı eşiği (USD)."
  type        = number
  default     = 200
}

variable "budget_alert_email" {
  description = "Bütçe alarmı e-postası. Boşsa bütçe kaynağı oluşturulmaz."
  type        = string
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "app_domain" {
  description = "Uygulamanın genel alan adı (ör. filo.ornek.com.tr). ACM sertifikası bu adı kapsamalı; web ve API aynı kökten sunulur."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9.-]+$", var.app_domain))
    error_message = "app_domain yalnızca küçük harf, rakam, nokta ve tire içermelidir (şema olmadan)."
  }
}

variable "web_desired_count" {
  type    = number
  default = 1
}

variable "scheduler_desired_count" {
  description = "Scheduler replika sayısı (0 veya 1; ek replikalar kilit nedeniyle boşta kalır)."
  type        = number
  default     = 1
  validation {
    condition     = contains([0, 1], var.scheduler_desired_count)
    error_message = "scheduler_desired_count 0 veya 1 olmalıdır."
  }
}

variable "smtp_host" {
  description = "İşlemsel e-posta sağlayıcısının SMTP sunucusu."
  type        = string
}

variable "smtp_port" {
  type    = number
  default = 587
}

variable "smtp_from" {
  description = "Gönderen adresi (alan adı SPF/DKIM ile doğrulanmış olmalı)."
  type        = string
}

variable "smtp_username" {
  type    = string
  default = ""
}

variable "field_encryption_primary_key_id" {
  description = "app-secrets içindeki field_encryption_keys JSON'unda birincil anahtar kimliği."
  type        = string
  default     = "k1"
}

variable "github_repository" {
  description = "owner/repo; boş değilse GitHub Actions OIDC dağıtım rolü oluşturulur."
  type        = string
  default     = ""
}
