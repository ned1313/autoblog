variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "autoblog"
}

variable "environment" {
  description = "Deployment environment (dev, test, prod)"
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "eastus"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default = {
    environment = "development"
    project     = "autoblog"
  }
}

variable "podcast_rss_url" {
  description = "URL of the podcast RSS feed to monitor"
  type        = string
}

variable "schedule_expression" {
  description = "CRON expression for the function schedule"
  type        = string
  default     = "0 0 */6 * * *" # Every 6 hours
}

variable "github_token" {
  description = "GitHub personal access token"
  type        = string
  sensitive   = true
}

variable "github_repo_owner" {
  description = "GitHub repository owner"
  type        = string
}

variable "github_repo_name" {
  description = "GitHub repository name"
  type        = string
}

variable "posts_path_pattern" {
  description = "Path pattern for blog posts in the repository"
  type        = string
  default     = "content/posts"
}

variable "template_file_path" {
  description = "Path to the blog post template file"
  type        = string
  default     = "templates/blog-template.md"
}