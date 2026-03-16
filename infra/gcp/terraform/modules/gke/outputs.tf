output "cluster_name"      { value = google_container_cluster.main.name }
output "cluster_endpoint"  { value = google_container_cluster.main.endpoint; sensitive = true }
output "app_sa_email"      { value = google_service_account.app.email }
