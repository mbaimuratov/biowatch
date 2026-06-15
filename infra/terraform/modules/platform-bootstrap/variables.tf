variable "environment" {
  description = "Environment name: dev or prod"
  type        = string
}

variable "gateway_api_version" {
  description = "Gateway API release version to install"
  type        = string
}

variable "argocd_chart_version" {
  description = "Pinned Argo CD Helm chart version"
  type        = string
}

variable "sealed_secrets_chart_version" {
  description = "Pinned sealed-secrets Helm chart version"
  type        = string
}

variable "argocd_values_file" {
  description = "Path to Argo CD Helm values file"
  type        = string
}

variable "sealed_secrets_values_file" {
  description = "Path to sealed-secrets Helm values file"
  type        = string
}

variable "traefik_values_file" {
  description = "Path to k3s Traefik HelmChartConfig valuesContent file"
  type        = string
}