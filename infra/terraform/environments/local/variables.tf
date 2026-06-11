variable "project_name" {
  description = "Name used to identify local BioWatch infrastructure resources."
  type        = string
  default     = "biowatch"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "local"
}
