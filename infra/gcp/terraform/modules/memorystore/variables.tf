variable "name_prefix"     { type = string }
variable "region"          { type = string }
variable "network_id"      { type = string }
variable "redis_tier"      { type = string; default = "STANDARD_HA" }
variable "redis_memory_gb" { type = number; default = 2 }
