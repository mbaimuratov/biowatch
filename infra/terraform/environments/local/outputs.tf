output "project_name" {
  description = "Project name for the local Terraform environment."
  value       = var.project_name
}

output "environment" {
  description = "Environment name for this Terraform configuration."
  value       = var.environment
}

output "prometheus_url" {
  value = "http://localhost:9090"
}

output "grafana_url" {
  value = "http://localhost:13000"
}

output "grafana_login" {
  value = "admin / admin"
}
