resource "google_storage_bucket" "documents" {
  name          = "${var.name_prefix}-documents-${var.project_id}"
  location      = var.region
  storage_class = "STANDARD"
  force_destroy = false

  versioning {
    enabled = true
  }

  uniform_bucket_level_access = true

  lifecycle_rule {
    action { type = "SetStorageClass"; storage_class = "NEARLINE" }
    condition { age = 30 }
  }

  lifecycle_rule {
    action { type = "SetStorageClass"; storage_class = "COLDLINE" }
    condition { age = 90 }
  }
}

# Block all public access
resource "google_storage_bucket_iam_binding" "no_public" {
  bucket  = google_storage_bucket.documents.name
  role    = "roles/storage.objectViewer"
  members = []
}
