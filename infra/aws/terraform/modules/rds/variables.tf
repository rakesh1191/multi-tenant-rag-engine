variable "name_prefix"    { type = string }
variable "vpc_id"         { type = string }
variable "subnet_ids"     { type = list(string) }
variable "allowed_sg_ids" { type = list(string) }
variable "db_name"        { type = string }
variable "instance_class" { type = string }
