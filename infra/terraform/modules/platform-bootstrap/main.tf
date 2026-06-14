locals {
  argocd_namespace         = "argocd"
  sealed_secrets_namespace = "sealed-secrets"

  labels = {
    "app.kubernetes.io/managed-by" = "terraform"
    "app.kubernetes.io/part-of"    = "biowatch"
    "environment"                  = var.environment
  }
}

data "http" "gateway_api_standard_install" {
  url = "https://github.com/kubernetes-sigs/gateway-api/releases/download/${var.gateway_api_version}/standard-install.yaml"
}

data "kubectl_file_documents" "gateway_api_standard_install" {
  content = data.http.gateway_api_standard_install.response_body
}

resource "kubectl_manifest" "gateway_api_crds" {
  for_each = data.kubectl_file_documents.gateway_api_standard_install.manifests

  yaml_body         = each.value
  server_side_apply = true
}

resource "kubectl_manifest" "argocd_namespace" {
  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name   = local.argocd_namespace
      labels = local.labels
    }
  })

  server_side_apply = true
}

resource "kubectl_manifest" "sealed_secrets_namespace" {
  yaml_body = yamlencode({
    apiVersion = "v1"
    kind       = "Namespace"
    metadata = {
      name   = local.sealed_secrets_namespace
      labels = local.labels
    }
  })

  server_side_apply = true
}

resource "kubectl_manifest" "traefik_helm_chart_config" {
  yaml_body = yamlencode({
    apiVersion = "helm.cattle.io/v1"
    kind       = "HelmChartConfig"
    metadata = {
      name      = "traefik"
      namespace = "kube-system"
      labels    = local.labels
    }
    spec = {
      valuesContent = file(var.traefik_values_file)
    }
  })

  depends_on = [
    kubectl_manifest.gateway_api_crds
  ]
}

resource "helm_release" "sealed_secrets" {
  name       = "sealed-secrets"
  namespace  = local.sealed_secrets_namespace
  repository = "https://bitnami-labs.github.io/sealed-secrets"
  chart      = "sealed-secrets"
  version    = var.sealed_secrets_chart_version

  values = [
    file(var.sealed_secrets_values_file)
  ]

  atomic          = true
  cleanup_on_fail = true
  timeout         = 600

  depends_on = [
    kubectl_manifest.sealed_secrets_namespace
  ]
}

resource "helm_release" "argocd" {
  name       = "argocd"
  namespace  = local.argocd_namespace
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = var.argocd_chart_version

  values = [
    file(var.argocd_values_file)
  ]

  atomic          = true
  cleanup_on_fail = true
  timeout         = 600

  depends_on = [
    kubectl_manifest.argocd_namespace
  ]
}
