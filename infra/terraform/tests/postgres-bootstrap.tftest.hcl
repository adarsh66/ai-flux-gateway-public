mock_provider "azurerm" {
  override_during = plan
  mock_data "azurerm_resource_group" {
    defaults = {
      id       = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-test"
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
      id = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-test/providers/Microsoft.ApiManagement/service/aiflux-test-apim"
    }
  }
  mock_resource "azurerm_container_registry" {
    defaults = {
      id = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-test/providers/Microsoft.ContainerRegistry/registries/aifluxtestacr"
    }
  }
  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      id           = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/test"
      client_id    = "00000000-0000-0000-0000-000000000002"
      principal_id = "00000000-0000-0000-0000-000000000003"
    }
  }
  mock_resource "azurerm_subnet" {
    defaults = {
      id = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-test/providers/Microsoft.Network/virtualNetworks/test/subnets/integration"
    }
  }
  mock_resource "azurerm_postgresql_flexible_server" {
    defaults = {
      id   = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-test/providers/Microsoft.DBforPostgreSQL/flexibleServers/aiflux-test-pg"
      fqdn = "aiflux-test-pg.postgres.database.azure.com"
    }
  }
  mock_resource "azurerm_eventhub_namespace" {
    defaults = {
      id = "/subscriptions/4d75ed7f-75ab-4db6-b1f3-263f240d1450/resourceGroups/rg-aiflux-test/providers/Microsoft.EventHub/namespaces/aiflux-test-eh"
    }
  }
}

mock_provider "azapi" {}

variables {
  subscription_id                                = "4d75ed7f-75ab-4db6-b1f3-263f240d1450"
  resource_group_name                            = "rg-aiflux-test"
  location                                       = "eastus"
  name_prefix                                    = "aiflux-test"
  deployment_approved                            = true
  manual_rbac_verified                           = false
  deployment_stage                               = "prerequisites"
  publisher_email                                = "test@example.invalid"
  gateway_origin_hostname                        = "test.example.invalid"
  apim_capacity                                  = 1
  app_service_sku                                = "B1"
  log_retention_days                             = 30
  create_container_registry                      = true
  database_engine                                = "postgresql"
  retain_legacy_mssql                            = true
  sql_sku                                        = "S0"
  turnstile_platform_enabled                     = true
  control_plane_worker_enabled                   = false
  operator_ip                                    = "167.103.66.114"
  hybrid_private_data_enabled                    = true
  sql_public_network_access_enabled              = false
  key_vault_public_network_access_enabled        = false
  function_storage_public_network_access_enabled = false
  local_auth_enabled                             = false
  sql_admin = {
    login     = "reviewed-dba"
    object_id = "00000000-0000-0000-0000-000000000007"
    tenant_id = "00000000-0000-0000-0000-000000000001"
  }
  network = {
    address_space                  = "10.50.0.0/16"
    app_gateway_subnet             = "10.50.0.0/24"
    private_endpoint_subnet        = "10.50.2.0/24"
    app_service_integration_subnet = "10.50.3.0/24"
  }
}

run "postgres_private_by_default" {
  command = plan
  assert {
    condition     = !azurerm_postgresql_flexible_server.main[0].public_network_access_enabled && length(azurerm_postgresql_flexible_server_firewall_rule.bootstrap) == 0 && !azurerm_mssql_server.main[0].public_network_access_enabled
    error_message = "Default configuration must keep both databases private without a PostgreSQL firewall exception."
  }
}

run "single_ip_bootstrap_does_not_open_other_services" {
  command = plan
  variables {
    postgres_bootstrap_public_ipv4 = "167.103.66.114"
    sql_firewall_ipv4s             = { ignored-for-postgres = "8.8.8.8" }
  }
  assert {
    condition     = azurerm_postgresql_flexible_server.main[0].public_network_access_enabled && length(azurerm_postgresql_flexible_server_firewall_rule.bootstrap) == 1 && azurerm_postgresql_flexible_server_firewall_rule.bootstrap[0].start_ip_address == "167.103.66.114" && azurerm_postgresql_flexible_server_firewall_rule.bootstrap[0].end_ip_address == "167.103.66.114"
    error_message = "PostgreSQL bootstrap must allow exactly the reviewed IPv4."
  }
  assert {
    condition     = !azurerm_mssql_server.main[0].public_network_access_enabled && length(azurerm_mssql_firewall_rule.operator) == 0 && length(azurerm_mssql_firewall_rule.apps) == 0 && !azurerm_key_vault.main.public_network_access_enabled && azapi_resource.function_storage[0].body.properties.publicNetworkAccess == "Disabled" && azapi_resource.function_storage[0].body.properties.networkAcls.bypass == "None"
    error_message = "PostgreSQL exception must not open MSSQL/vault/storage or add trusted-service bypasses."
  }
  assert {
    condition     = length(azurerm_linux_web_app.main) == 0 && length(azurerm_linux_function_app.control_plane) == 0 && !output.central_rbac_handoff.runtime_gate_attested
    error_message = "Schema bootstrap must not activate workloads or attest central grants."
  }
}

run "reject_cidr" {
  command = plan
  variables {
    postgres_bootstrap_public_ipv4 = "167.103.66.114/32"
  }
  expect_failures = [var.postgres_bootstrap_public_ipv4]
}

run "reject_ipv6" {
  command = plan
  variables {
    postgres_bootstrap_public_ipv4 = "2001:db8::1"
  }
  expect_failures = [var.postgres_bootstrap_public_ipv4]
}

run "reject_azure_services_wildcard" {
  command = plan
  variables {
    postgres_bootstrap_public_ipv4 = "0.0.0.0"
  }
  expect_failures = [var.postgres_bootstrap_public_ipv4]
}

run "reject_invalid_ipv4" {
  command = plan
  variables {
    postgres_bootstrap_public_ipv4 = "999.1.1.1"
  }
  expect_failures = [var.postgres_bootstrap_public_ipv4]
}

run "reject_bootstrap_during_runtime_activation" {
  command = plan
  variables {
    postgres_bootstrap_public_ipv4 = "167.103.66.114"
    deployment_stage               = "platform"
    manual_rbac_verified           = true
    entra = {
      audience            = "api://test"
      client_id           = "00000000-0000-0000-0000-000000000002"
      home_tenant_id      = "00000000-0000-0000-0000-000000000001"
      bootstrap_object_id = "00000000-0000-0000-0000-000000000007"
    }
    apps = {
      api      = { image = "test/api@sha256:0000000000000000000000000000000000000000000000000000000000000000", registry_url = "https://test.azurecr.io", port = 8000, health_path = "/health" }
      customer = { image = "test/customer@sha256:0000000000000000000000000000000000000000000000000000000000000000", registry_url = "https://test.azurecr.io", port = 8080, health_path = "/healthz" }
      admin    = { image = "test/admin@sha256:0000000000000000000000000000000000000000000000000000000000000000", registry_url = "https://test.azurecr.io", port = 8080, health_path = "/healthz" }
    }
  }
  expect_failures = [var.postgres_bootstrap_public_ipv4]
}

run "remove_exception_restores_private" {
  command = plan
  variables {
    postgres_bootstrap_public_ipv4 = null
  }
  assert {
    condition     = !azurerm_postgresql_flexible_server.main[0].public_network_access_enabled && length(azurerm_postgresql_flexible_server_firewall_rule.bootstrap) == 0
    error_message = "Removing the temporary input must close public PostgreSQL and remove its single firewall rule."
  }
}