resource "aws_ecr_repository" "api" {
  name                 = "${var.name_prefix}-api"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  tags = { Name = "${var.name_prefix}-api" }
}

resource "aws_ecr_repository" "ui" {
  name                 = "${var.name_prefix}-ui"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  tags = { Name = "${var.name_prefix}-ui" }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [
      { rulePriority = 1, description = "Keep last 10 tagged images",
        selection = { tagStatus = "tagged", tagPrefixList = ["v"], countType = "imageCountMoreThan", countNumber = 10 },
        action = { type = "expire" } },
      { rulePriority = 2, description = "Remove untagged after 7 days",
        selection = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 7 },
        action = { type = "expire" } }
    ]
  })
}

resource "aws_ecr_lifecycle_policy" "ui" {
  repository = aws_ecr_repository.ui.name
  policy     = aws_ecr_lifecycle_policy.api.policy
}
