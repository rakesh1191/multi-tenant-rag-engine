project_id   = "your-gcp-project-id"
region       = "us-central1"
environment  = "staging"

subnet_cidr   = "10.10.0.0/20"
pods_cidr     = "10.11.0.0/16"
services_cidr = "10.12.0.0/20"

db_tier       = "db-custom-2-7680"
db_name       = "ragdb"

redis_tier      = "STANDARD_HA"
redis_memory_gb = 2

gke_machine_type = "n2-standard-2"
gke_min_nodes    = 1
gke_max_nodes    = 5
