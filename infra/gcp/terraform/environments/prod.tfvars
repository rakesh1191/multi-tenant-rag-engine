project_id   = "your-gcp-project-id"
region       = "us-central1"
environment  = "prod"

subnet_cidr   = "10.0.0.0/20"
pods_cidr     = "10.1.0.0/16"
services_cidr = "10.2.0.0/20"

db_tier       = "db-custom-4-15360"
db_name       = "ragdb"

redis_tier      = "STANDARD_HA"
redis_memory_gb = 4

gke_machine_type = "n2-standard-4"
gke_min_nodes    = 2
gke_max_nodes    = 20
