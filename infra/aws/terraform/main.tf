locals {
  name_prefix = "${var.project}-${var.environment}"
  azs         = slice(data.aws_availability_zones.available.names, 0, 3)
}

data "aws_availability_zones" "available" {
  state = "available"
}

# ── Networking ──────────────────────────────────────────────────────────────

module "networking" {
  source      = "./modules/networking"
  name_prefix = local.name_prefix
  vpc_cidr    = var.vpc_cidr
  azs         = local.azs
}

# ── Container Registry ──────────────────────────────────────────────────────

module "ecr" {
  source      = "./modules/ecr"
  name_prefix = local.name_prefix
}

# ── Database — Aurora PostgreSQL 16 ─────────────────────────────────────────

module "rds" {
  source             = "./modules/rds"
  name_prefix        = local.name_prefix
  vpc_id             = module.networking.vpc_id
  subnet_ids         = module.networking.private_subnet_ids
  allowed_sg_ids     = [module.eks.node_security_group_id]
  db_name            = var.db_name
  instance_class     = var.db_instance_class
}

# ── Cache — ElastiCache Redis 7 ─────────────────────────────────────────────

module "elasticache" {
  source         = "./modules/elasticache"
  name_prefix    = local.name_prefix
  vpc_id         = module.networking.vpc_id
  subnet_ids     = module.networking.private_subnet_ids
  allowed_sg_ids = [module.eks.node_security_group_id]
  node_type      = var.redis_node_type
}

# ── Object Storage — S3 ─────────────────────────────────────────────────────

module "s3" {
  source      = "./modules/s3"
  name_prefix = local.name_prefix
  region      = var.aws_region
}

# ── Kubernetes — EKS ────────────────────────────────────────────────────────

module "eks" {
  source                 = "./modules/eks"
  name_prefix            = local.name_prefix
  vpc_id                 = module.networking.vpc_id
  private_subnet_ids     = module.networking.private_subnet_ids
  public_subnet_ids      = module.networking.public_subnet_ids
  node_instance_type     = var.eks_node_instance_type
  min_nodes              = var.eks_min_nodes
  max_nodes              = var.eks_max_nodes
  s3_bucket_arn          = module.s3.bucket_arn
}
