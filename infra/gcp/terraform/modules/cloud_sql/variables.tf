variable "name_prefix" { type = string }
variable "region"      { type = string }
variable "network_id"  { type = string }
variable "db_tier"     { type = string; default = "db-custom-2-7680" }
variable "db_name"     { type = string; default = "ragdb" }
