variable "name_prefix"        { type = string }
variable "vpc_id"             { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "public_subnet_ids"  { type = list(string) }
variable "node_instance_type" { type = string; default = "t3.xlarge" }
variable "min_nodes"          { type = number; default = 2 }
variable "max_nodes"          { type = number; default = 10 }
variable "s3_bucket_arn"      { type = string }
