resource "docker_image" "this" {
  name = var.image
}

resource "docker_container" "this" {
  name  = var.name
  image = docker_image.this.image_id

  dynamic "ports" {
    for_each = var.ports

    content {
      internal = ports.value.internal
      external = ports.value.external
    }
  }

  dynamic "volumes" {
    for_each = var.volumes

    content {
      host_path      = volumes.value.host_path
      container_path = volumes.value.container_path
      read_only      = volumes.value.read_only
    }
  }

  env = var.env

  command = var.command

  networks_advanced {
    name = var.network_name
  }
}