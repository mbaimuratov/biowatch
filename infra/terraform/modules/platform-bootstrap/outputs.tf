output "argocd_namespace" {
  value = "argocd"
}

output "sealed_secrets_namespace" {
  value = "sealed-secrets"
}

output "argocd_release_name" {
  value = helm_release.argocd.name
}

output "sealed_secrets_release_name" {
  value = helm_release.sealed_secrets.name
}

output "gateway_class_name" {
  value = "traefik"
}
