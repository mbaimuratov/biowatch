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

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - "biowatch-tf-alertmanager:9093"

rule_files:
  - /etc/prometheus/alerts.yml

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

  volumes {
    host_path      = abspath(local_file.prometheus_alerts.filename)
    container_path = "/etc/prometheus/alerts.yml"
    read_only      = true
  }

  networks_advanced {
    name = docker_network.private_network.name
  }

  depends_on = [
    local_file.prometheus_config,
    local_file.prometheus_alerts,
    docker_container.alertmanager
  ]
}

resource "local_file" "grafana_datasource" {
  filename = "${path.module}/generated/grafana/provisioning/datasources/prometheus.yml"

  content = <<EOF
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://biowatch-tf-prometheus:9090
    isDefault: true
    editable: true
EOF
}

resource "docker_image" "grafana" {
  name = "grafana/grafana:11.4.0"
}

resource "docker_container" "grafana" {
  name  = "biowatch-tf-grafana"
  image = docker_image.grafana.image_id

  ports {
    internal = 3000
    external = 13000
  }

  env = [
    "GF_SECURITY_ADMIN_USER=admin",
    "GF_SECURITY_ADMIN_PASSWORD=admin",
    "GF_USERS_ALLOW_SIGN_UP=false"
  ]

  volumes {
    host_path      = abspath("${path.module}/generated/grafana/provisioning")
    container_path = "/etc/grafana/provisioning"
    read_only      = true
  }

  networks_advanced {
    name = docker_network.private_network.name
  }

  depends_on = [
    docker_container.prometheus,
    local_file.grafana_datasource
  ]
}

resource "local_file" "alertmanager_config" {
  filename = "${path.module}/generated/alertmanager/alertmanager.yml"

  content = <<EOF
global:
  resolve_timeout: 5m

route:
  receiver: "default"
  group_by: ["alertname", "severity"]
  group_wait: 10s
  group_interval: 1m
  repeat_interval: 1h

receivers:
  - name: "default"
EOF
}

resource "docker_image" "alertmanager" {
  name = "prom/alertmanager:v0.27.0"
}

resource "docker_container" "alertmanager" {
  name  = "biowatch-tf-alertmanager"
  image = docker_image.alertmanager.image_id

  ports {
    internal = 9093
    external = 19093
  }

  volumes {
    host_path      = abspath(local_file.alertmanager_config.filename)
    container_path = "/etc/alertmanager/alertmanager.yml"
    read_only      = true
  }

  command = [
    "--config.file=/etc/alertmanager/alertmanager.yml"
  ]

  networks_advanced {
    name = docker_network.private_network.name
  }

  depends_on = [
    local_file.alertmanager_config
  ]
}

resource "local_file" "prometheus_alerts" {
  filename = "${path.module}/generated/alerts.yml"

  content = <<EOF
groups:
  - name: local-test
    rules:
      - alert: PrometheusAlwaysFiring
        expr: vector(1)
        for: 30s
        labels:
          severity: warning
        annotations:
          summary: "Test alert is firing"
          description: "This alert always fires locally to verify Prometheus -> Alertmanager wiring."
EOF
}