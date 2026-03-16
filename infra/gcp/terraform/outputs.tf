output "cluster_name"       { value = module.gke.cluster_name }
output "api_image_repo"     { value = module.artifact_registry.api_repo_url }
output "ui_image_repo"      { value = module.artifact_registry.ui_repo_url }
output "db_connection_name" { value = module.cloud_sql.connection_name; sensitive = true }
output "redis_host"         { value = module.memorystore.host; sensitive = true }
output "gcs_bucket"         { value = module.gcs.bucket_name }
