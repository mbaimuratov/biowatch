module "platform_bootstrap" {
  source = "../../modules/platform-bootstrap"

  environment = "prod"

  gateway_api_version          = var.gateway_api_version
  argocd_chart_version         = var.argocd_chart_version
  sealed_secrets_chart_version = var.sealed_secrets_chart_version

  argocd_values_file         = "${path.module}/values/argocd.yaml"
  sealed_secrets_values_file = "${path.module}/values/sealed-secrets.yaml"
  traefik_values_file        = "${path.module}/values/traefik.yaml"
}