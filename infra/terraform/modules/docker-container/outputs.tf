output "name" {
  value = docker_container.this.name
}

output "id" {
  value = docker_container.this.id
}

output "image" {
  value = docker_image.this.name
}