output "argocd_namespace" {
  value = module.platform_bootstrap.argocd_namespace
}

output "sealed_secrets_namespace" {
  value = module.platform_bootstrap.sealed_secrets_namespace
}

output "gateway_class_name" {
  value = module.platform_bootstrap.gateway_class_name
}

output "argocd_port_forward_command" {
  value = "kubectl --kubeconfig ${var.kubeconfig_path} -n argocd port-forward svc/argocd-server 8080:80"
}

output "dev_root_app_apply_command" {
  value = "kubectl --kubeconfig ${var.kubeconfig_path} apply -f infra/gitops/root/root-app-dev.yaml"
}