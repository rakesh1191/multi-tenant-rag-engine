region      = "us-east-1"
environment = "staging"
vpc_cidr    = "10.1.0.0/16"

# RDS
db_instance_class = "db.t4g.medium"
db_name           = "ragdb"

# ElastiCache
redis_node_type   = "cache.t4g.micro"

# EKS
node_instance_type = "t3.large"
min_nodes          = 1
max_nodes          = 5
