region      = "us-east-1"
environment = "prod"
vpc_cidr    = "10.0.0.0/16"

# RDS
db_instance_class = "db.r6g.large"
db_name           = "ragdb"

# ElastiCache
redis_node_type   = "cache.r6g.large"

# EKS
node_instance_type = "t3.xlarge"
min_nodes          = 2
max_nodes          = 20
