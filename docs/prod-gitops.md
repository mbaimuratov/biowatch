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
- Strimzi/Kafka: receives BioWatch domain events from the outbox publisher.
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

BioWatch publishes paper ingestion events through the outbox publisher
Deployment. Production values enable Kafka with:

```text
BIOWATCH_KAFKA_ENABLED=true
BIOWATCH_KAFKA_BOOTSTRAP_SERVERS=biowatch-kafka-kafka-bootstrap.kafka-prod.svc.cluster.local:9092
BIOWATCH_KAFKA_CLIENT_ID=biowatch-prod
BIOWATCH_KAFKA_INDEXER_TOPIC=biowatch.paper.ingested.v1
BIOWATCH_KAFKA_INDEXER_GROUP_ID=biowatch-indexer
```

The publisher reads pending rows from `event_outbox`, publishes them to
`biowatch.paper.ingested.v1`, and records `published_at` or retry metadata on
the row.

The indexer consumer Deployment reads `biowatch.paper.ingested.v1`, loads each
paper from Postgres, upserts it into Elasticsearch with the paper id as the
document id, and commits Kafka offsets only after Elasticsearch indexing
succeeds. Production keeps this consumer at one replica.

Useful Kubernetes checks:

```sh
kubectl get pods -A
kubectl get applications.argoproj.io -n argocd
kubectl get appprojects.argoproj.io -n argocd
```

## Git-Only Image Promotion

`main` is the integration branch. Merging to `main` publishes a multi-arch GHCR
image, but it does not deploy production.

Production Argo CD tracks the `prod` branch. After the image workflow succeeds
on `main`, the promotion workflow opens a PR into `prod`. That PR contains the
matching chart/code changes and updates:

```text
infra/gitops/environments/prod/values.yaml
```

The production image tag must be a full commit SHA:

```yaml
image:
  repository: ghcr.io/mbaimuratov/biowatch
  tag: <commit-sha>
```

The promotion PR validates:

- the GHCR image exists
- `linux/amd64` and `linux/arm64` are present
- Helm renders successfully for `biowatch-prod`
- every BioWatch workload uses the promoted image tag

Merge the promotion PR into `prod` to deploy. Argo CD detects the `prod` branch
change and syncs `biowatch-prod`.

Rollback is also Git-only: revert the promotion merge on `prod`, or promote an
earlier known-good commit SHA with a new promotion PR.

## Initial Prod Branch Cutover

After the clean promotion workflow lands on `main`, create the long-lived
production branch from that commit:

```sh
git fetch origin main
git switch --detach origin/main
git push origin HEAD:prod
```

Argo CD then tracks `prod` for the BioWatch application. Future production
rollouts come from promotion PRs into `prod`, not direct changes on `main`.

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
CI, merge to `prod`, and Argo CD sync.
