variable "project_name" {
  type    = string
  default = "sentellent"
}

variable "environment" {
  type    = string
  default = "staging"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "vpc_id" {
  type        = string
  description = "Existing VPC ID for ECS, RDS, and Redis."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for data and compute resources."
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_name" {
  type    = string
  default = "sentellent"
}

variable "db_username" {
  type    = string
  default = "sentellent_user"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "backend_image" {
  type        = string
  description = "ECR image URI for the backend container."
}

variable "backend_desired_count" {
  type    = number
  default = 1
}

variable "jwt_secret_arn" {
  type = string
}

variable "groq_api_key_arn" {
  type = string
}

variable "google_oauth_client_id_arn" {
  type = string
}

variable "google_oauth_client_secret_arn" {
  type = string
}

variable "github_repository_url" {
  type        = string
  default     = ""
  description = "Optional GitHub repository URL to connect Amplify for automatic builds."
}

variable "amplify_branch_name" {
  type        = string
  default     = "main"
  description = "Git branch Amplify deploys for the frontend."
}

variable "backend_api_url" {
  type        = string
  description = "Public backend API base URL (API Gateway endpoint) injected into Amplify and OAuth settings."
}
