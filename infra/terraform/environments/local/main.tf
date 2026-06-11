locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "local_file" "terraform_readme" {
  filename = "${path.module}/generated/terraform-managed.txt"
  content  = "Managed by Terraform\n"
}