#!/usr/bin/env bash
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/biowatch-utm-k3s.yaml}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEALED_SECRET_FILE="$ROOT_DIR/infra/gitops/environments/prod/sealed-secret.yaml"

echo "== Checking cluster access =="
command -v kubectl >/dev/null || { echo "kubectl is required"; exit 1; }
command -v helm >/dev/null || { echo "helm is required"; exit 1; }
kubectl version --client=true >/dev/null
kubectl get nodes >/dev/null

echo "== Installing ingress-nginx =="
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx >/dev/null
helm repo update >/dev/null
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --version 4.11.3 \
  --set controller.service.type=LoadBalancer
kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=300s

echo "== Installing Argo CD =="
helm repo add argo https://argoproj.github.io/argo-helm >/dev/null
helm repo update >/dev/null
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install argocd argo/argo-cd \
  --namespace argocd \
  --version 9.3.7 \
  -f "$ROOT_DIR/infra/argocd/values.yaml"
kubectl -n argocd rollout status deploy/argocd-server --timeout=300s
kubectl -n argocd rollout status deploy/argocd-repo-server --timeout=300s
kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=300s

echo "== Installing Sealed Secrets =="
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets >/dev/null
helm repo update >/dev/null
helm upgrade --install sealed-secrets sealed-secrets/sealed-secrets \
  --namespace sealed-secrets \
  --create-namespace \
  --version 2.17.3
kubectl -n sealed-secrets rollout status deploy/sealed-secrets --timeout=300s

echo "== Applying prod namespace and sealed secret =="
kubectl create namespace biowatch-prod --dry-run=client -o yaml | kubectl apply -f -
if [[ ! -s "$SEALED_SECRET_FILE" ]]; then
  echo "Missing $SEALED_SECRET_FILE"
  echo "Run scripts/seal-prod-secret.sh first, then commit the encrypted SealedSecret."
  exit 1
fi
kubectl apply -f "$SEALED_SECRET_FILE"

echo "== Applying Argo CD project =="
kubectl apply -f "$ROOT_DIR/infra/gitops/projects/biowatch-project.yaml"

echo "== Bootstrapping root app =="
kubectl apply -f "$ROOT_DIR/infra/gitops/root/root-app.yaml"

echo "== Final status =="
kubectl get pods -A
kubectl get applications.argoproj.io -n argocd || true
kubectl get appprojects.argoproj.io -n argocd || true
