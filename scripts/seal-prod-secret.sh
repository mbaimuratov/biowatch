#!/usr/bin/env bash
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/biowatch-utm-k3s.yaml}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_FILE="$ROOT_DIR/infra/gitops/environments/prod/sealed-secret.yaml"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: $name"
    exit 1
  fi
}

require_env BIOWATCH_TELEGRAM_BOT_TOKEN
require_env BIOWATCH_LLM_API_KEY

command -v kubectl >/dev/null || { echo "kubectl is required"; exit 1; }
command -v helm >/dev/null || { echo "helm is required"; exit 1; }
command -v kubeseal >/dev/null || { echo "kubeseal is required"; exit 1; }

POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-biowatch}"
BIOWATCH_DATABASE_URL="${BIOWATCH_DATABASE_URL:-postgresql+asyncpg://biowatch:${POSTGRES_PASSWORD}@biowatch-postgres:5432/biowatch}"
telegram_key="BIOWATCH_TELEGRAM_BOT_TOKEN"
llm_key="BIOWATCH_LLM_API_KEY"

tmp_dir="$(mktemp -d)"
cert_file="$tmp_dir/sealed-secrets-cert.pem"
secret_file="$tmp_dir/biowatch-secret.yaml"
trap 'rm -rf "$tmp_dir"' EXIT

echo "== Checking cluster access =="
kubectl get nodes >/dev/null

echo "== Ensuring Sealed Secrets controller =="
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets >/dev/null
helm repo update sealed-secrets >/dev/null
helm upgrade --install sealed-secrets sealed-secrets/sealed-secrets \
  --namespace sealed-secrets \
  --create-namespace \
  --version 2.17.3 >/dev/null
kubectl -n sealed-secrets rollout status deploy/sealed-secrets --timeout=300s

echo "== Fetching Sealed Secrets public certificate =="
kubeseal \
  --fetch-cert \
  --controller-name sealed-secrets \
  --controller-namespace sealed-secrets \
  >"$cert_file"

echo "== Building temporary Secret manifest =="
kubectl -n biowatch-prod create secret generic biowatch-secret \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --from-literal=BIOWATCH_DATABASE_URL="$BIOWATCH_DATABASE_URL" \
  --from-literal="${telegram_key}=$BIOWATCH_TELEGRAM_BOT_TOKEN" \
  --from-literal="${llm_key}=$BIOWATCH_LLM_API_KEY" \
  --dry-run=client \
  -o yaml \
  >"$secret_file"

mkdir -p "$(dirname "$OUTPUT_FILE")"

echo "== Sealing prod Secret =="
kubeseal \
  --cert "$cert_file" \
  --format yaml \
  <"$secret_file" \
  >"$OUTPUT_FILE"

echo "== Checking for plaintext secret leakage =="
if grep -R -F -- "$BIOWATCH_TELEGRAM_BOT_TOKEN" \
  "$ROOT_DIR/infra/gitops" "$ROOT_DIR/infra/helm" "$ROOT_DIR/.github" "$ROOT_DIR/scripts" "$ROOT_DIR/docs" \
  >/dev/null; then
  echo "Plaintext Telegram token found after sealing. Refusing to continue."
  exit 1
fi

if grep -R -F -- "$BIOWATCH_LLM_API_KEY" \
  "$ROOT_DIR/infra/gitops" "$ROOT_DIR/infra/helm" "$ROOT_DIR/.github" "$ROOT_DIR/scripts" "$ROOT_DIR/docs" \
  >/dev/null; then
  echo "Plaintext LLM API key found after sealing. Refusing to continue."
  exit 1
fi

echo "Wrote encrypted SealedSecret to $OUTPUT_FILE"
