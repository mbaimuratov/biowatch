variable "kubeconfig_path" {
  description = "Path to dev cluster kubeconfig"
  type        = string
}

variable "kube_context" {
  description = "Optional kubeconfig context"
  type        = string
  default     = ""
}

variable "gateway_api_version" {
  description = "Gateway API release version"
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