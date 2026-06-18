terraform {
  required_version = ">= 1.8.0"

  required_providers {
    docker = {
      source = "kreuzwerker/docker"
    }
  }
}

provider "docker" {
  host = "unix:///Users/mac/.docker/run/docker.sock"
}