resource "google_artifact_registry_repository" "api" {
  repository_id = "${var.name_prefix}-api"
  location      = var.region
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-recent-10"
    action = "KEEP"
    most_recent_versions { keep_count = 10 }
  }
}

resource "google_artifact_registry_repository" "ui" {
  repository_id = "${var.name_prefix}-ui"
  location      = var.region
  format        = "DOCKER"

  cleanup_policies {
    id     = "keep-recent-10"
    action = "KEEP"
    most_recent_versions { keep_count = 10 }
  }
}
