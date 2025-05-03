provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = true
    }
  }
}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.project_name}-${var.environment}"
  location = var.location
  tags     = var.tags
}

# Storage account for function app
resource "azurerm_storage_account" "sa" {
  name                     = "sa${var.project_name}${var.environment}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = var.tags
}

# App Service Plan (Consumption plan for Function App)
resource "azurerm_service_plan" "asp" {
  name                = "asp-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  os_type             = "Linux"
  sku_name            = "Y1" # Consumption plan
  tags                = var.tags
}

# Key Vault for secrets
resource "azurerm_key_vault" "kv" {
  name                       = "kv-${var.project_name}-${var.environment}"
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  sku_name                   = "standard"
  tags                       = var.tags

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = [
      "Get", "List", "Set", "Delete", "Purge"
    ]
  }
}

data "azurerm_client_config" "current" {}

# Azure OpenAI service for blog post generation
resource "azurerm_cognitive_account" "openai" {
  name                = "ai-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  kind                = "OpenAI"
  sku_name            = "S0"
  tags                = var.tags
}

# OpenAI Deployment (GPT model for generating blog posts)
resource "azurerm_cognitive_deployment" "gpt_deployment" {
  name                 = "gpt-deployment"
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = "gpt-4-32k"  # Using 16k model for larger context window
    version = "0613"              # Updated version with larger context support
  }

  sku {
    name     = "Standard"
    capacity = 1
  }
}

# Function App
resource "azurerm_linux_function_app" "function_app" {
  name                = "func-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location

  storage_account_name       = azurerm_storage_account.sa.name
  storage_account_access_key = azurerm_storage_account.sa.primary_access_key
  service_plan_id            = azurerm_service_plan.asp.id

  app_settings = {
    "FUNCTIONS_WORKER_RUNTIME"       = "python"
    "APPINSIGHTS_INSTRUMENTATIONKEY" = azurerm_application_insights.insights.instrumentation_key
    "KeyVaultName"                   = azurerm_key_vault.kv.name
    "OPENAI_ENDPOINT"                = azurerm_cognitive_account.openai.endpoint
    "OPENAI_DEPLOYMENT_NAME"         = azurerm_cognitive_deployment.gpt_deployment.name
    "PODCAST_RSS_URL"                = var.podcast_rss_url
    "SCHEDULE"                       = var.schedule_expression
    "GITHUB_REPO_OWNER"              = var.github_repo_owner
    "GITHUB_REPO_NAME"               = var.github_repo_name
    "POSTS_PATH_PATTERN"             = var.posts_path_pattern
    "TEMPLATE_FILE_PATH"             = var.template_file_path
  }

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.10"
    }
    application_insights_connection_string = azurerm_application_insights.insights.connection_string
    application_insights_key               = azurerm_application_insights.insights.instrumentation_key
  }

  tags = var.tags
}

# Application Insights
resource "azurerm_application_insights" "insights" {
  name                = "appi-${var.project_name}-${var.environment}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  application_type    = "web"
  tags                = var.tags
}

# Grant Function App identity access to Key Vault
resource "azurerm_key_vault_access_policy" "function_kv_access" {
  key_vault_id = azurerm_key_vault.kv.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_linux_function_app.function_app.identity[0].principal_id

  secret_permissions = [
    "Get", "List"
  ]
}

# Grant Function App access to OpenAI
resource "azurerm_role_assignment" "function_openai_access" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services User"
  principal_id         = azurerm_linux_function_app.function_app.identity[0].principal_id
}

# Store GitHub token in Key Vault
resource "azurerm_key_vault_secret" "github_token" {
  name         = "github-token"
  value        = var.github_token
  key_vault_id = azurerm_key_vault.kv.id
}

# Store OpenAI key in Key Vault
resource "azurerm_key_vault_secret" "openai_key" {
  name         = "openai-key"
  value        = azurerm_cognitive_account.openai.primary_access_key
  key_vault_id = azurerm_key_vault.kv.id
}