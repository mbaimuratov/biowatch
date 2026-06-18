variable "name" {
  description = "Docker container name"
  type        = string
}

variable "image" {
  description = "Docker image name and tag"
  type        = string
}

variable "network_name" {
  description = "Docker network name"
  type        = string
}

variable "ports" {
  description = "Container port mappings"
  type = list(object({
    internal = number
    external = number
  }))
  default = []
}

variable "volumes" {
  description = "Container volume mounts"
  type = list(object({
    host_path      = string
    container_path = string
    read_only      = bool
  }))
  default = []
}

variable "env" {
  description = "Environment variables"
  type        = list(string)
  default     = []
}

variable "command" {
  description = "Container command override"
  type        = list(string)
  default     = null
}