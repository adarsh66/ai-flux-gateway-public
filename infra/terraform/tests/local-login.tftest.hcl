# Independent local-login coverage; preserve the user's rebuild test.
mock_provider "azurerm" {
  override_during = plan
  mock_data "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-fdpo-dev"
      location = "eastus"
    }
  }
  mock_data "azurerm_client_config" {
    defaults = {
      subscription_id = "4d75ed7f-75ab-4db6-b1f3-263f240d1450"
      tenant_id       = "00000000-0000-0000-0000-000000000001"
    }
  }
  mock_resource "azurerm_api_management" {
    defaults = {
      id = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-fdpo-dev/providers/Microsoft.ApiManagement/service/aiflux-test-apim"
    }
  }
  mock_resource "azurerm_container_registry" {
    defaults = {
      id = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-fdpo-dev/providers/Microsoft.ContainerRegistry/registries/aifluxtestacr"
    }
  }
  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      id           = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-fdpo-dev/providers/Microsoft.ManagedIdentity/userAssignedIdentities/test"
      client_id    = "00000000-0000-0000-0000-000000000002"
      principal_id = "00000000-0000-0000-0000-000000000003"
    }
  }
  mock_resource "azurerm_application_insights" {
    defaults = {
      id                = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-fdpo-dev/providers/Microsoft.Insights/components/test"
      connection_string = "InstrumentationKey=00000000-0000-0000-0000-000000000004"
    }
  }
  mock_resource "azurerm_subnet" {
    defaults = {
      id = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-fdpo-dev/providers/Microsoft.Network/virtualNetworks/test/subnets/integration"
    }
  }
  mock_resource "azurerm_postgresql_flexible_server" {
    defaults = {
      id   = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-fdpo-dev/providers/Microsoft.DBforPostgreSQL/flexibleServers/aiflux-test-pg"
      fqdn = "aiflux-test-pg.postgres.database.azure.com"
    }
  }
  mock_resource "azurerm_eventhub_namespace" {
    defaults = {
      id = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-fdpo-dev/providers/Microsoft.EventHub/namespaces/aiflux-test-eh"
    }
  }
}
mock_provider "azapi" {}

variables {
  subscription_id                                = "4d75ed7f-75ab-4db6-b1f3-263f240d1450"
  resource_group_name                            = "rg-aiflux-fdpo-dev"
  location                                       = "eastus"
  name_prefix                                    = "aiflux-test"
  publisher_email                                = "test@example.invalid"
  deployment_approved                            = true
  manual_rbac_verified                           = true
  deployment_stage                               = "platform"
  gateway_origin_hostname                        = "test.example.invalid"
  operator_ip                                    = "167.103.66.114"
  log_retention_days                             = 30
  apim_capacity                                  = 1
  app_service_sku                                = "B1"
  create_container_registry                      = true
  turnstile_platform_enabled                     = true
  hybrid_private_data_enabled                    = true
  private_api_enabled                            = true
  sql_public_network_access_enabled              = false
  key_vault_public_network_access_enabled        = false
  function_storage_public_network_access_enabled = false
  entra                                          = null
  local_auth_enabled                             = true
  database_engine                                = "postgresql"
  mise_sidecar_enabled                           = false
  sql_admin = {
    login     = "human-bootstrap-admin"
    object_id = "00000000-0000-0000-0000-000000000007"
    tenant_id = "00000000-0000-0000-0000-000000000001"
  }
  network = {
    address_space                  = "10.50.0.0/16"
    app_gateway_subnet             = "10.50.0.0/24"
    private_endpoint_subnet        = "10.50.2.0/24"
    app_service_integration_subnet = "10.50.3.0/24"
  }
  apps = {
    api      = { image = "test/api@sha256:0000000000000000000000000000000000000000000000000000000000000000", registry_url = "https://test.azurecr.io", port = 8000, health_path = "/health" }
    customer = { image = "test/customer@sha256:0000000000000000000000000000000000000000000000000000000000000000", registry_url = "https://test.azurecr.io", port = 8080, health_path = "/healthz" }
    admin    = { image = "test/admin@sha256:0000000000000000000000000000000000000000000000000000000000000000", registry_url = "https://test.azurecr.io", port = 8080, health_path = "/healthz" }
  }
  local_auth = {
    jwt_secret_uri                  = "https://test.vault.azure.net/secrets/local-jwt"
    bootstrap_admin_password_uri    = "https://test.vault.azure.net/secrets/bootstrap-admin"
    bootstrap_customer_password_uri = "https://test.vault.azure.net/secrets/bootstrap-customer"
    bootstrap_admin_email           = "admin@example.invalid"
    bootstrap_customer_email        = "customer@example.invalid"
    bootstrap_customer_org          = "Test Customer"
  }
}

run "local_login_without_portal_registration" {
  command = plan
  assert {
    condition     = azurerm_linux_web_app.main["api"].app_settings["AIFLUX_ENTRA_AUDIENCE"] == "local://turnstile-postgres-auth" && azurerm_linux_web_app.main["api"].app_settings["AIFLUX_HOME_TENANT_ID"] == "00000000-0000-0000-0000-000000000001" && azurerm_linux_web_app.main["api"].app_settings["AIFLUX_ENTRA_CLIENT_ID"] == "" && azurerm_linux_web_app.main["api"].app_settings["AIFLUX_BOOTSTRAP_OBJECT_ID"] == ""
    error_message = "Local login must not require or bootstrap an Entra portal registration."
  }
  assert {
    condition     = azurerm_linux_web_app.main["api"].app_settings["AZURE_CLIENT_ID"] == azurerm_user_assigned_identity.identity["api"].client_id && length(azapi_resource.api_sidecar) == 0 && !azurerm_linux_web_app.main["api"].public_network_access_enabled
    error_message = "Local login must retain managed identity and private API ingress without an Entra sidecar."
  }
}

run "reject_local_login_with_entra_sidecar" {
  command = plan
  variables {
    mise_sidecar_enabled = true
  }
  expect_failures = [var.local_auth_enabled]
}

run "direct_signing_without_vault_or_bootstrap_passwords" {
  command = plan
  variables {
    local_auth       = null
    local_jwt_secret = "synthetic-test-signing-9G7b2K4v5H8n1T6s"
  }
  assert {
    condition     = azurerm_linux_web_app.main["api"].app_settings["AIFLUX_LOCAL_JWT_SECRET"] == var.local_jwt_secret && azurerm_linux_web_app.main["api"].app_settings["AIFLUX_LOCAL_AUTH_ENABLED"] == "true"
    error_message = "The direct signing secret must be configured only on the API."
  }
  assert {
    condition = alltrue([for name in ["api", "admin", "customer"] :
      !contains(keys(azurerm_linux_web_app.main[name].app_settings), "AIFLUX_BOOTSTRAP_ADMIN_PASSWORD") &&
      !contains(keys(azurerm_linux_web_app.main[name].app_settings), "AIFLUX_BOOTSTRAP_CUSTOMER_PASSWORD")
    ]) && alltrue([for name in ["admin", "customer"] : !contains(keys(azurerm_linux_web_app.main[name].app_settings), "AIFLUX_LOCAL_JWT_SECRET")])
    error_message = "Bootstrap passwords must not reach runtime and JWT signing must stay off frontend apps."
  }
}

run "key_vault_jwt_only" {
  command = plan
  variables {
    local_auth = { jwt_secret_uri = "https://test.vault.azure.net/secrets/local-jwt" }
  }
  assert {
    condition     = azurerm_linux_web_app.main["api"].app_settings["AIFLUX_LOCAL_JWT_SECRET"] == "@Microsoft.KeyVault(SecretUri=https://test.vault.azure.net/secrets/local-jwt)" && !contains(keys(azurerm_linux_web_app.main["api"].app_settings), "AIFLUX_BOOTSTRAP_ADMIN_PASSWORD")
    error_message = "Key Vault JWT configuration must not require bootstrap passwords."
  }
}

run "reject_missing_jwt_source" {
  command = plan
  variables {
    local_auth = null
  }
  expect_failures = [var.local_auth_enabled]
}

run "reject_ambiguous_jwt_sources" {
  command = plan
  variables {
    local_jwt_secret = "synthetic-test-signing-9G7b2K4v5H8n1T6s"
  }
  expect_failures = [var.local_auth_enabled]
}

run "reject_weak_direct_signing_secret" {
  command = plan
  variables {
    local_auth       = null
    local_jwt_secret = "weak"
  }
  expect_failures = [var.local_jwt_secret]
}