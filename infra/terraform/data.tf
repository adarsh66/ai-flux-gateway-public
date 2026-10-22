resource "azurerm_mssql_server" "main" {
  count                                    = local.mssql_stage ? 1 : 0
  name                                     = "${local.prefix}-sql"
  resource_group_name                      = local.rg
  location                                 = local.sql_location
  version                                  = "12.0"
  minimum_tls_version                      = "1.2"
  public_network_access_enabled            = var.sql_public_network_access_enabled
  connection_policy                        = var.hybrid_private_data_enabled ? "Proxy" : "Default"
  express_vulnerability_assessment_enabled = var.sql_express_vulnerability_assessment_enabled
  tags                                     = local.tags
  identity {
    type = "SystemAssigned"
  }
  azuread_administrator {
    login_username              = var.sql_admin.login
    object_id                   = var.sql_admin.object_id
    tenant_id                   = var.sql_admin.tenant_id
    azuread_authentication_only = true
  }
  depends_on = [terraform_data.approval]
}

resource "azurerm_mssql_database" "main" {
  count     = local.mssql_stage ? 1 : 0
  name      = "aiflux"
  server_id = azurerm_mssql_server.main[0].id
  sku_name  = var.sql_sku
  tags      = local.tags
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_postgresql_flexible_server" "main" {
  count                         = local.postgres_stage ? 1 : 0
  name                          = "${local.prefix}-pg"
  resource_group_name           = local.rg
  location                      = local.sql_location
  version                       = "16"
  sku_name                      = var.postgres_sku
  storage_mb                    = 32768
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = var.sql_public_network_access_enabled
  zone                          = "1"
  tags                          = local.tags
  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
    tenant_id                     = var.sql_admin.tenant_id
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.identity["api"].id]
  }
  depends_on = [terraform_data.approval]
}

resource "azurerm_postgresql_flexible_server_active_directory_administrator" "main" {
  count               = local.postgres_stage ? 1 : 0
  server_name         = azurerm_postgresql_flexible_server.main[0].name
  resource_group_name = local.rg
  tenant_id           = var.sql_admin.tenant_id
  object_id           = var.sql_admin.object_id
  principal_name      = var.sql_admin.login
  principal_type      = "User"
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  count     = local.postgres_stage ? 1 : 0
  name      = "turnstile"
  server_id = azurerm_postgresql_flexible_server.main[0].id
  charset   = "UTF8"
  collation = "en_US.utf8"
  lifecycle {
    prevent_destroy = true
  }
}

resource "azapi_resource" "function_storage" {
  count     = local.prerequisites_stage ? 1 : 0
  type      = "Microsoft.Storage/storageAccounts@2025-01-01"
  parent_id = local.rg_id
  name      = "${local.compact}func"
  location  = var.location
  tags      = local.tags
  body = {
    kind = "StorageV2"
    sku  = { name = "Standard_LRS" }
    properties = {
      minimumTlsVersion            = "TLS1_2"
      supportsHttpsTrafficOnly     = true
      allowBlobPublicAccess        = false
      allowSharedKeyAccess         = false
      publicNetworkAccess          = var.function_storage_public_network_access_enabled ? "Enabled" : "Disabled"
      defaultToOAuthAuthentication = true
      networkAcls = {
        defaultAction       = "Allow"
        bypass              = var.turnstile_platform_enabled ? "AzureServices" : "None"
        ipRules             = []
        virtualNetworkRules = []
      }
    }
  }
  depends_on = [terraform_data.approval]
}

resource "azapi_resource" "turnstile_ledger" {
  count     = local.turnstile_stage ? 1 : 0
  type      = "Microsoft.Storage/storageAccounts/tableServices/tables@2025-01-01"
  parent_id = "${azapi_resource.function_storage[0].id}/tableServices/default"
  name      = var.ledger_table_name
}

resource "azapi_resource" "model_routes" {
  count     = local.turnstile_stage ? 1 : 0
  type      = "Microsoft.Storage/storageAccounts/tableServices/tables@2025-01-01"
  parent_id = "${azapi_resource.function_storage[0].id}/tableServices/default"
  name      = "ModelRoutes"
}

resource "azurerm_eventhub_namespace" "main" {
  count                         = local.turnstile_stage ? 1 : 0
  name                          = "${local.prefix}-eh"
  location                      = var.location
  resource_group_name           = local.rg
  sku                           = "Standard"
  capacity                      = 1
  auto_inflate_enabled          = true
  maximum_throughput_units      = 2
  public_network_access_enabled = true
  local_authentication_enabled  = false
  minimum_tls_version           = "1.2"
  tags                          = local.tags
  depends_on                    = [terraform_data.approval]
}

resource "azurerm_eventhub" "token_usage" {
  count             = local.turnstile_stage ? 1 : 0
  name              = "token-usage"
  namespace_id      = azurerm_eventhub_namespace.main[0].id
  partition_count   = 4
  message_retention = 7
}

resource "azurerm_api_management_logger" "eventhub" {
  count               = local.turnstile_stage ? 1 : 0
  name                = "finops-token-usage-eventhub"
  api_management_name = azurerm_api_management.main.name
  resource_group_name = local.rg
  resource_id         = azurerm_eventhub_namespace.main[0].id
  eventhub {
    name                             = azurerm_eventhub.token_usage[0].name
    endpoint_uri                     = "https://${azurerm_eventhub_namespace.main[0].name}.servicebus.windows.net"
    user_assigned_identity_client_id = azurerm_user_assigned_identity.identity["gateway"].client_id
  }
}

resource "azurerm_mssql_firewall_rule" "operator" {
  count            = local.mssql_stage && var.sql_public_network_access_enabled ? 1 : 0
  name             = "reviewed-operator"
  server_id        = azurerm_mssql_server.main[0].id
  start_ip_address = var.operator_ip
  end_ip_address   = var.operator_ip
}

resource "azurerm_mssql_firewall_rule" "apps" {
  for_each         = local.platform_stage && local.mssql_stage && var.sql_public_network_access_enabled ? var.sql_firewall_ipv4s : {}
  name             = "app-${each.key}"
  server_id        = azurerm_mssql_server.main[0].id
  start_ip_address = each.value
  end_ip_address   = each.value
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "operator" {
  count            = local.postgres_stage && var.sql_public_network_access_enabled ? 1 : 0
  name             = "reviewed-operator"
  server_id        = azurerm_postgresql_flexible_server.main[0].id
  start_ip_address = var.operator_ip
  end_ip_address   = var.operator_ip
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "apps" {
  for_each         = local.platform_stage && local.postgres_stage && var.sql_public_network_access_enabled ? var.sql_firewall_ipv4s : {}
  name             = "app-${each.key}"
  server_id        = azurerm_postgresql_flexible_server.main[0].id
  start_ip_address = each.value
  end_ip_address   = each.value
}

locals {
  app_sql_outbound_ipv4s = local.platform_stage ? toset(concat(
    flatten([for app in values(azurerm_linux_web_app.main) : app.possible_outbound_ip_address_list]),
    azurerm_linux_function_app.ingestion[0].possible_outbound_ip_address_list,
    local.turnstile_stage ? azurerm_linux_function_app.control_plane[0].possible_outbound_ip_address_list : [],
  )) : toset([])
}

resource "terraform_data" "sql_firewall_gate" {
  count = local.public_edge_stage && !var.hybrid_private_data_enabled ? 1 : 0
  lifecycle {
    precondition {
      condition     = length(local.app_sql_outbound_ipv4s) > 0 && length(setsubtract(local.app_sql_outbound_ipv4s, toset(values(var.sql_firewall_ipv4s)))) == 0
      error_message = "Before public edge approval, capture all platform possible outbound IPv4 addresses and add reviewed exact-address SQL firewall rules in a second platform plan."
    }
  }
  depends_on = [azurerm_mssql_firewall_rule.apps, azurerm_postgresql_flexible_server_firewall_rule.apps]
}
