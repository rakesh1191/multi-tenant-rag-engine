output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "ecr_api_url" {
  value = module.ecr.api_repo_url
}

output "ecr_ui_url" {
  value = module.ecr.ui_repo_url
}

output "rds_endpoint" {
  value     = module.rds.cluster_endpoint
  sensitive = true
}

output "redis_endpoint" {
  value     = module.elasticache.primary_endpoint
  sensitive = true
}

output "s3_bucket_name" {
  value = module.s3.bucket_name
}
