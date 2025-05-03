terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
  cloud {
    organization = "ned-in-the-cloud"
    workspaces {
      name = "autoblog"
    }
  }
}