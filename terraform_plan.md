# Terraform Integration Plan for BioWatch

Goal: integrate Terraform into BioWatch without replacing Helm, Argo CD, or GitOps.

Boundary:

```text
Terraform = provisions infrastructure
Helm = packages Kubernetes resources
Argo CD = deploys apps/platform components into Kubernetes
GitHub Actions = builds/tests/images/promotion
```

Terraform should not manage BioWatch Deployments, KafkaTopics, Argo CD Applications, or Helm app releases already controlled by GitOps.

---

## Step 1 — Add Terraform project skeleton

Create:

```text
infra/terraform/
  README.md
  modules/
  environments/
    local/
    prod/
```

Add base files:

```text
infra/terraform/environments/local/
  providers.tf
  variables.tf
  outputs.tf
  main.tf
  terraform.tfvars.example
```

Expected outcome:

```text
Terraform folder exists.
terraform init works.
No real infrastructure is created yet.
```

Commands:

```bash
cd infra/terraform/environments/local
terraform init
terraform fmt -recursive
terraform validate
```

Why:

```text
Start with clean Terraform structure before touching real resources.
```

---

## Step 2 — Learn Terraform state using local files

Add a harmless resource:

```hcl
resource "local_file" "terraform_readme" {
  filename = "${path.module}/generated/terraform-managed.txt"
  content  = "Managed by Terraform\n"
}
```

Expected outcome:

```text
terraform apply creates a local file.
terraform destroy removes it.
terraform state list shows the resource.
```

Commands:

```bash
terraform plan
terraform apply
terraform state list
terraform destroy
```

Why:

```text
This teaches Terraform state, plan/apply/destroy, and resource lifecycle without cloud cost.
```

---

## Step 3 — Add Docker provider for local learning

Add Docker provider in `local`.

Use Terraform to create a Docker network:

```text
biowatch-tf-monitoring
```

Expected outcome:

```text
Terraform creates and destroys a Docker network.
```

Commands:

```bash
terraform init
terraform plan
terraform apply
docker network ls | grep biowatch-tf
terraform destroy
```

Why:

```text
Docker provider gives real infrastructure behavior without cloud setup.
```

---

## Step 4 — Manage local observability containers with Terraform

Use Terraform to run:

```text
Prometheus
Grafana
Alertmanager
```

Only for local Terraform learning.

Do not replace existing Compose permanently yet.

Expected outcome:

```text
terraform apply starts Prometheus/Grafana/Alertmanager containers.
Prometheus UI opens on localhost:9090.
Grafana opens on localhost:3000.
Alertmanager opens on localhost:9093.
terraform destroy removes them.
```

Why:

```text
This connects Terraform to something already familiar: observability.
```

Important:

```text
This is a learning environment, not the final BioWatch production deployment.
```

---

## Step 5 — Extract reusable Docker modules

Create modules:

```text
infra/terraform/modules/docker-network/
infra/terraform/modules/docker-container/
```

Root module should call:

```hcl
module "monitoring_network" {}

module "prometheus" {}
module "grafana" {}
module "alertmanager" {}
```

Expected outcome:

```text
Same local monitoring stack works through modules.
```

Why:

```text
Modules teach reusable infrastructure structure.
```

---

## Step 6 — Add Terraform validation CI

Add GitHub Actions workflow:

```text
.github/workflows/terraform.yml
```

Run:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

Expected outcome:

```text
PRs fail if Terraform formatting or validation breaks.
```

Why:

```text
Terraform must be checked before merge, same as app code.
```

Do not run `terraform apply` in CI yet.

---

## Step 7 — Add production infrastructure skeleton

Create:

```text
infra/terraform/environments/prod/
  providers.tf
  backend.tf
  variables.tf
  outputs.tf
  main.tf
  terraform.tfvars.example
```

For now, keep backend local or commented.

Expected outcome:

```text
prod environment exists but does not provision cloud resources yet.
```

Why:

```text
Separate local learning from real production infrastructure.
```

Rule:

```text
local = Docker learning
prod = real infrastructure later
```

---

## Step 8 — Provision one real VPS

Use Terraform to create one VPS.

Terraform should manage:

```text
server
SSH key
firewall
public IP output
```

Do not install BioWatch yet.

Expected outcome:

```text
terraform apply creates a server.
ssh works.
terraform destroy removes the server.
```

Outputs:

```text
server_ip
ssh_command
```

Why:

```text
This is the first real infrastructure layer under BioWatch.
```

---

## Step 9 — Bootstrap server for Kubernetes

Use cloud-init or remote-exec only for minimal bootstrap:

```text
install k3s
install kubectl
open required ports
output kubeconfig retrieval command
```

Terraform should not deploy BioWatch.

Expected outcome:

```text
terraform apply creates a VPS with k3s installed.
kubectl can connect.
```

Why:

```text
Terraform creates the machine and Kubernetes base.
Argo CD will own application deployment after bootstrap.
```

---

## Step 10 — Bootstrap Argo CD and hand off to GitOps

Add a bootstrap script:

```text
infra/terraform/scripts/bootstrap_argocd.sh
```

It should:

```text
install Argo CD
apply root-app.yaml
point Argo CD to the prod branch
```

Expected final flow:

```text
terraform apply
  ↓
VPS exists
  ↓
k3s installed
  ↓
Argo CD installed
  ↓
root-app.yaml applied
  ↓
Argo CD deploys BioWatch, Kafka, observability, and platform apps
```

Why:

```text
This creates the correct production boundary:
Terraform provisions infrastructure.
Argo CD reconciles Kubernetes apps.
```

Final verification:

```bash
kubectl get nodes
kubectl get pods -n argocd
kubectl get applications -n argocd
```

Expected:

```text
node Ready
argocd pods Running
biowatch-root Synced/Healthy
```

---

# Final target architecture

```text
Terraform
  ↓
VPS / firewall / SSH / k3s
  ↓
Argo CD bootstrap
  ↓
GitOps from prod branch
  ↓
BioWatch stack:
  API
  workers
  PostgreSQL
  Redis
  Elasticsearch
  Kafka / Strimzi
  Prometheus
  Grafana
  Alertmanager
```

---

# What Terraform must NOT manage

```text
Do not manage BioWatch Kubernetes Deployments.
Do not manage KafkaTopic resources.
Do not manage Argo CD Applications after bootstrap.
Do not manage app config already controlled by Helm values/GitOps.
Do not store secrets in tfvars.
Do not use Terraform as a deployment tool.
```

---

# Completion criteria

Terraform integration is complete when:

```text
1. Local Terraform exercises work.
2. Terraform CI validates fmt/init/validate.
3. Prod Terraform structure exists.
4. Terraform can create a real server.
5. Terraform can bootstrap k3s.
6. Argo CD can be installed/bootstrap-applied.
7. BioWatch deployment is handed off to GitOps.
8. README explains exact commands and boundaries.
```
