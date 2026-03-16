locals {
  name_prefix = "rag-${var.environment}"
}

module "networking" {
  source       = "./modules/networking"
  name_prefix  = local.name_prefix
  region       = var.region
  subnet_cidr  = var.subnet_cidr
  pods_cidr    = var.pods_cidr
  services_cidr = var.services_cidr
}

module "artifact_registry" {
  source      = "./modules/artifact_registry"
  name_prefix = local.name_prefix
  region      = var.region
  project_id  = var.project_id
}

module "cloud_sql" {
  source      = "./modules/cloud_sql"
  name_prefix = local.name_prefix
  region      = var.region
  network_id  = module.networking.network_id
  db_tier     = var.db_tier
  db_name     = var.db_name
}

module "memorystore" {
  source          = "./modules/memorystore"
  name_prefix     = local.name_prefix
  region          = var.region
  network_id      = module.networking.network_id
  redis_tier      = var.redis_tier
  redis_memory_gb = var.redis_memory_gb
}

module "gcs" {
  source      = "./modules/gcs"
  name_prefix = local.name_prefix
  region      = var.region
  project_id  = var.project_id
}

module "gke" {
  source            = "./modules/gke"
  name_prefix       = local.name_prefix
  region            = var.region
  project_id        = var.project_id
  network_id        = module.networking.network_id
  subnet_id         = module.networking.subnet_id
  pods_range_name   = module.networking.pods_range_name
  services_range_name = module.networking.services_range_name
  machine_type      = var.gke_machine_type
  min_nodes         = var.gke_min_nodes
  max_nodes         = var.gke_max_nodes
  gcs_bucket_name   = module.gcs.bucket_name
}
