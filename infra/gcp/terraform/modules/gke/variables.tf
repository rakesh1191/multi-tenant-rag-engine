variable "name_prefix"          { type = string }
variable "region"               { type = string }
variable "project_id"           { type = string }
variable "network_id"           { type = string }
variable "subnet_id"            { type = string }
variable "pods_range_name"      { type = string }
variable "services_range_name"  { type = string }
variable "machine_type"         { type = string; default = "n2-standard-4" }
variable "min_nodes"            { type = number; default = 1 }
variable "max_nodes"            { type = number; default = 10 }
variable "gcs_bucket_name"      { type = string }
