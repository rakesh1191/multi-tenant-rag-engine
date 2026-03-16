output "api_repo_url" { value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}" }
output "ui_repo_url"  { value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.ui.repository_id}" }
