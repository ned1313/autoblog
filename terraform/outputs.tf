output "function_app_name" {
  description = "Name of the Azure Function App"
  value       = azurerm_linux_function_app.function_app.name
}

output "function_app_default_hostname" {
  description = "Default hostname of the function app"
  value       = azurerm_linux_function_app.function_app.default_hostname
}

output "openai_endpoint" {
  description = "Endpoint for the Azure OpenAI service"
  value       = azurerm_cognitive_account.openai.endpoint
}

output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.kv.name
}

output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.rg.name
}

output "application_insights_connection_string" {
  description = "Connection string for Application Insights"
  value       = azurerm_application_insights.insights.connection_string
  sensitive   = true
}