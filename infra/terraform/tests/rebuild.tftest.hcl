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
  deployment_approved                            = true
  manual_rbac_verified                           = true
  deployment_stage                               = "platform"
  publisher_email                                = "test@example.invalid"
  gateway_origin_hostname                        = "test.example.invalid"
  apim_capacity                                  = 1
  app_service_sku                                = "B1"
  log_retention_days                             = 30
  create_container_registry                      = true
  database_engine                                = "postgresql"
  turnstile_platform_enabled                     = true
  private_api_enabled                            = true
  operator_ip                                    = "167.103.66.114"
  hybrid_private_data_enabled                    = true
  sql_public_network_access_enabled              = false
  key_vault_public_network_access_enabled        = false
  function_storage_public_network_access_enabled = false
  local_auth_enabled                             = true
  local_auth = {
    jwt_secret_uri                  = "https://test.vault.azure.net/secrets/local-jwt"
    bootstrap_admin_password_uri    = "https://test.vault.azure.net/secrets/bootstrap-admin"
    bootstrap_customer_password_uri = "https://test.vault.azure.net/secrets/bootstrap-customer"
    bootstrap_admin_email           = "admin@example.invalid"
    bootstrap_customer_email        = "customer@example.invalid"
    bootstrap_customer_org          = "Test Customer"
  }
  entra = {
    audience            = "api://test"
    client_id           = "00000000-0000-0000-0000-000000000005"
    home_tenant_id      = "00000000-0000-0000-0000-000000000001"
    bootstrap_object_id = "00000000-0000-0000-0000-000000000006"
  }
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
}

run "private_rebuild_security_and_auth" {
  command = plan
  assert {
    condition     = !azurerm_linux_web_app.main["api"].public_network_access_enabled && length(azurerm_linux_web_app.main["api"].site_config[0].ip_restriction) == 0 && azurerm_linux_web_app.main["api"].site_config[0].ip_restriction_default_action == "Deny"
    error_message = "API public ingress must stay disabled and deny all."
  }
  assert {
    condition     = azurerm_linux_web_app.main["admin"].site_config[0].ip_restriction_default_action == "Deny" && length(azurerm_linux_web_app.main["admin"].site_config[0].ip_restriction) == 1 && one(azurerm_linux_web_app.main["admin"].site_config[0].ip_restriction).ip_address == "167.103.66.114/32"
    error_message = "Admin must allow only the approved /32."
  }
  assert {
    condition     = alltrue([for app in values(azurerm_linux_web_app.main) : app.virtual_network_subnet_id == azurerm_subnet.app_service_integration[0].id && app.site_config[0].scm_ip_restriction_default_action == "Deny" && length(app.site_config[0].scm_ip_restriction) == 0 && !app.site_config[0].scm_use_main_ip_restriction])
    error_message = "Every portal needs private API reachability, without opening SCM."
  }
  assert {
    condition     = azurerm_linux_web_app.main["api"].app_settings["AIFLUX_LOCAL_AUTH_ENABLED"] == "true" && startswith(azurerm_linux_web_app.main["api"].app_settings["AIFLUX_LOCAL_JWT_SECRET"], "@Microsoft.KeyVault(SecretUri=") && startswith(local.database_url, "postgresql://aiflux-test-api-identity@") && startswith(azurerm_linux_function_app.ingestion[0].app_settings["AIFLUX_DATABASE_URL"], "postgresql://aiflux-test-ingestion-identity@") && startswith(azurerm_linux_function_app.control_plane[0].app_settings["DATABASE_URL"], "postgresql://aiflux-test-control-plane-identity@")
    error_message = "Production local auth requires vault references and each SQL caller's own managed identity."
  }
}

run "reject_unconfigured_local_auth" {
  command = plan
  variables {
    local_auth = null
  }
  expect_failures = [var.local_auth_enabled]
}

run "resource_provisioning_before_central_grants" {
  command = plan
  variables {
    deployment_stage        = "prerequisites"
    manual_rbac_verified    = false
    retain_legacy_mssql     = true
    sql_sku                 = "S0"
    local_auth_enabled      = false
    local_auth              = null
    entra                   = null
    apps                    = {}
    gateway_origin_hostname = ""
  }
  assert {
    condition     = length(azurerm_linux_web_app.main) == 0 && length(azurerm_linux_function_app.ingestion) == 0 && length(azurerm_linux_function_app.control_plane) == 0
    error_message = "Resource-only graph must not activate workloads; existing apps require the guarded targeted plan."
  }
  assert {
    condition     = length(azurerm_postgresql_flexible_server.main) == 1 && length(azurerm_mssql_server.main) == 1 && contains(keys(azurerm_user_assigned_identity.identity), "control-plane")
    error_message = "Provision PostgreSQL and identities without deleting legacy MSSQL."
  }
  assert {
    condition     = azurerm_private_dns_zone.data["sql"].name == "privatelink.database.windows.net" && azurerm_private_dns_zone.data["postgres"].name == "privatelink.postgres.database.azure.com" && !azurerm_eventhub_namespace.main[0].public_network_access_enabled && length(azurerm_private_endpoint.eventhub) == 1
    error_message = "Retain private MSSQL and add private PostgreSQL/Event Hubs without public exposure."
  }
  assert {
    condition     = !output.central_rbac_handoff.runtime_gate_attested && alltrue([for request in output.central_rbac_handoff.assignments : request.status == "request-only-not-verified"])
    error_message = "Handoff requests must not attest grants or enable runtime."
  }
  assert {
    condition     = azapi_resource.function_storage[0].body.properties.networkAcls.bypass == "None" && azapi_resource.function_storage[0].body.properties.publicNetworkAccess == "Disabled" && !azapi_resource.function_storage[0].body.properties.allowSharedKeyAccess
    error_message = "Provisioning Turnstile must not add a trusted-service bypass or enable public/shared-key storage access."
  }
  assert {
    condition     = output.central_rbac_handoff.owner == "central-team-external" && length(output.central_rbac_handoff.assignments) > 0 && alltrue([for request in output.central_rbac_handoff.assignments : request.principal_id == azurerm_user_assigned_identity.identity[request.identity].principal_id && startswith(request.scope, local.rg_id) && startswith(request.role_definition_id, "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/")])
    error_message = "Central requests must identify actual managed identities and resource-scoped grants without creating assignments."
  }
}

run "runtime_activation_requires_central_verification" {
  command = plan
  variables {
    manual_rbac_verified = false
  }
  expect_failures = [terraform_data.approval]
}