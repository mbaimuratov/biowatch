locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "local_file" "terraform_readme" {
  filename = "${path.module}/generated/terraform-managed.txt"
  content  = "Managed by Terraform\n"
}

resource "docker_network" "private_network" {
  name = "biowatch-tf-monitoring"
}

resource "local_file" "prometheus_config" {
  filename = "${path.module}/generated/prometheus.yml"

  content = <<EOF
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]
EOF
}

resource "docker_image" "prometheus" {
  name = "prom/prometheus:v3.0.1"
}

resource "docker_container" "prometheus" {
  name  = "biowatch-tf-prometheus"
  image = docker_image.prometheus.image_id

  ports {
    internal = 9090
    external = 9090
  }

  volumes {
    host_path      = abspath(local_file.prometheus_config.filename)
    container_path = "/etc/prometheus/prometheus.yml"
    read_only      = true
  }

  networks_advanced {
    name = docker_network.private_network.name
  }

  depends_on = [
    local_file.prometheus_config
  ]
}