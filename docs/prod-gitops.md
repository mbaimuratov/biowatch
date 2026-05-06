# BioWatch Production GitOps

BioWatch production runs on a single-node k3s cluster inside a UTM Ubuntu VM.
The Mac workstation is used only for one-time bootstrap and Git changes.

## Architecture

- Mac workstation: runs `kubectl`, `helm`, `kubeseal`, `argocd`, and Git.
- UTM Ubuntu VM: hosts the k3s cluster at `192.168.106.3`.
- k3s: production Kubernetes runtime.
- ingress-nginx: exposes HTTP and HTTPS on the VM IP.
- Argo CD: reconciles BioWatch from Git.
- Sealed Secrets: stores encrypted Kubernetes Secret manifests in Git.
- GHCR: stores multi-arch BioWatch app images.
- BioWatch Helm chart: rendered by Argo CD from `infra/helm/biowatch`.

The production namespace is `biowatch-prod`. The environment name is `prod`.

## One-Time Bootstrap

Set the kubeconfig for the UTM k3s cluster. The scripts default to this path:

```sh
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/biowatch-utm-k3s.yaml}"
```

Create the encrypted production Secret from local environment variables:

```sh
read -rsp 'Telegram bot token: ' BIOWATCH_TELEGRAM_BOT_TOKEN
export BIOWATCH_TELEGRAM_BOT_TOKEN
read -rsp 'OpenAI API key: ' BIOWATCH_LLM_API_KEY
export BIOWATCH_LLM_API_KEY
./scripts/seal-prod-secret.sh
```

The sealing script installs or upgrades the pinned Sealed Secrets controller if
it is not already present, then uses its public certificate to create the
encrypted Secret manifest. By default it writes an in-cluster database URL that
points at the production Helm release's Postgres Service.

The sealing script writes only encrypted data to:

```text
infra/gitops/environments/prod/sealed-secret.yaml
```

Commit the encrypted `sealed-secret.yaml` if it changed. Do not commit plaintext
tokens, API keys, PEM files, or temporary Secret YAML.

Bootstrap the platform controllers and root GitOps entrypoint:

```sh
./scripts/bootstrap-prod.sh
```

The bootstrap script installs or upgrades:

- `ingress-nginx`
- `argocd`
- `sealed-secrets`

It also applies the bootstrap prerequisites:

- `infra/gitops/environments/prod/sealed-secret.yaml`
- `infra/gitops/projects/biowatch-project.yaml`
- `infra/gitops/root/root-app.yaml`

The script intentionally does not run `helm upgrade biowatch ...`. BioWatch is
deployed by Argo CD from Git after bootstrap.

## Argo CD Login

Retrieve the initial admin password and login through nginx ingress:

```sh
export ARGOCD_PASSWORD="$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d)"
argocd login argocd.local --username admin --password "$ARGOCD_PASSWORD" --insecure --grpc-web
```

The Argo CD production values explicitly enable admin RBAC access for bootstrap:

```yaml
configs:
  rbac:
    policy.default: role:readonly
    policy.csv: |
      g, admin, role:admin
```

## Verify

Check Argo CD and BioWatch:

```sh
argocd app list --grpc-web
argocd app get biowatch-prod --grpc-web
kubectl get pods -n biowatch-prod
curl -H "Host: biowatch.local" http://192.168.106.3/health
```

Useful Kubernetes checks:

```sh
kubectl get pods -A
kubectl get applications.argoproj.io -n argocd
kubectl get appprojects.argoproj.io -n argocd
```

## Git-Only Image Promotion

Production image promotion is a Git change only.

1. Build and publish a new GHCR image through the image workflow.
2. Verify the selected image tag supports ARM64:

```sh
docker buildx imagetools inspect ghcr.io/mbaimuratov/biowatch:<commit-sha>
```

3. Edit only the image tag in:

```text
infra/helm/biowatch/values-prod.yaml
```

Example:

```yaml
image:
  repository: ghcr.io/mbaimuratov/biowatch
  tag: <commit-sha>
```

4. Open a PR.
5. Wait for CI.
6. Merge to `main`.
7. Argo CD detects the Git change and syncs `biowatch-prod`.
8. Kubernetes rolls out the new image.

## Forbidden Deployment Commands

Do not use these for BioWatch production changes:

```sh
helm upgrade biowatch ...
kubectl set image ...
kubectl patch deployment ...
kubectl edit deployment ...
```

Those commands mutate the cluster outside Git and break the intended production
source of truth. After bootstrap, production changes must flow through Git,
CI, merge to `main`, and Argo CD sync.
