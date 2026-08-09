locals {
  ownership_tags = {
    PortfolioEnvironment = var.environment
    PortfolioManaged     = "true"
    PortfolioPersistent  = "false"
    PortfolioRepository  = var.repository_identity
  }

  name             = "${var.name_prefix}-${var.environment}"
  runtime_sizing   = jsondecode(file("${path.module}/../runtime-sizing.json"))
  image_references = { for purpose, url in var.ecr_repository_urls : purpose => "${url}@${var.image_digests[purpose]}" }
}
