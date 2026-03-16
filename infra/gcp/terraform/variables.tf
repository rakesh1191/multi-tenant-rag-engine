variable "project_id"  { type = string; description = "GCP project ID" }
variable "region"      { type = string; default = "us-central1" }
variable "environment" { type = string; default = "prod" }

variable "subnet_cidr"          { type = string; default = "10.0.0.0/20" }
variable "pods_cidr"            { type = string; default = "10.1.0.0/16" }
variable "services_cidr"        { type = string; default = "10.2.0.0/20" }

variable "db_tier"              { type = string; default = "db-custom-2-7680" }
variable "db_name"              { type = string; default = "ragdb" }

variable "redis_tier"           { type = string; default = "STANDARD_HA" }
variable "redis_memory_gb"      { type = number; default = 2 }

variable "gke_machine_type"     { type = string; default = "n2-standard-4" }
variable "gke_min_nodes"        { type = number; default = 1 }
variable "gke_max_nodes"        { type = number; default = 10 }
