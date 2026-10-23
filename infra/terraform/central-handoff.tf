# Data-only requests, never Microsoft.Authorization resources. Scopes are intended
# ARM IDs, not evidence that a service or a grant exists. Principals come from Azure.
locals {
  central_builtin_roles = {
    "AcrPull"                        = "7f951dda-4ed3-4680-a7ca-43fe172d538d"
    "Key Vault Secrets User"         = "4633458b-17de-408a-b874-0445c86b69e6"
    "Log Analytics Reader"           = "73c42c96-874c-492b-b04d-ab87d138a893"
    "Monitoring Metrics Publisher"   = "3913510d-42f4-4e42-8a64-420c390055eb"
    "Cognitive Services User"        = "a97b65f3-24c7-4388-baec-2e87135dc908"
    "Storage Blob Data Owner"        = "b7e6dc6d-f1e8-4753-8033-0f276bb0955b"
    "Storage Queue Data Contributor" = "974c5e8b-45b9-4653-ba55-5f855dd0fb88"
    "Storage Table Data Contributor" = "0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3"
    "Azure Event Hubs Data Sender"   = "2b629674-e913-4c01-ae53-ef4638d8f975"
    "Azure Event Hubs Data Receiver" = "a638d3c7-ab3a-418d-83e6-5f17a39d4fde"
  }
  central_storage_scope = "${local.rg_id}/providers/Microsoft.Storage/storageAccounts/${local.compact}func"
  central_vault_scope   = "${local.rg_id}/providers/Microsoft.KeyVault/vaults/${local.compact}kv"
  central_apim_scope    = "${local.rg_id}/providers/Microsoft.ApiManagement/service/${local.apim_name}"
  central_event_scope   = "${local.rg_id}/providers/Microsoft.EventHub/namespaces/${local.prefix}-eh/eventhubs/token-usage"
  central_grant_requests = concat(
    [for name in local.identity_names : { identity = name, role = "Monitoring Metrics Publisher", scope = "${local.rg_id}/providers/Microsoft.Insights/components/${local.prefix}-insights" }],
    [for name in local.prerequisites_stage ? ["api", "ingestion"] : [] : { identity = name, role = "Log Analytics Reader", scope = "${local.rg_id}/providers/Microsoft.OperationalInsights/workspaces/${local.prefix}-logs" }],
    [for name in local.prerequisites_stage ? concat(["api", "customer", "admin", "ingestion"], local.turnstile_stage ? ["control-plane"] : []) : [] : { identity = name, role = "AcrPull", scope = local.registry_resource_id }],
    [for name in local.prerequisites_stage ? ["gateway", "api"] : ["gateway"] : { identity = name, role = "Key Vault Secrets User", scope = local.central_vault_scope }],
    flatten([for name in local.prerequisites_stage ? concat(["ingestion"], local.turnstile_stage ? ["control-plane"] : []) : [] : [
      for role in ["Storage Blob Data Owner", "Storage Queue Data Contributor", "Storage Table Data Contributor"] : { identity = name, role = role, scope = local.central_storage_scope }
    ]]),
    [for name in local.turnstile_stage ? ["gateway", "api"] : [] : { identity = name, role = "Storage Table Data Contributor", scope = local.central_storage_scope }],
    local.turnstile_stage ? [
      { identity = "gateway", role = "Azure Event Hubs Data Sender", scope = local.central_event_scope },
      { identity = "ingestion", role = "Azure Event Hubs Data Receiver", scope = local.central_event_scope },
    ] : [],
    [for service in concat(["safety"], var.protection_language_enabled ? ["foundry"] : []) : {
      identity = "gateway", role = "Cognitive Services User", scope = "${local.rg_id}/providers/Microsoft.CognitiveServices/accounts/${local.prefix}-${service}"
    }],
    local.edge_tls_stage ? [{ identity = "edge", role = "Key Vault Secrets User", scope = trimsuffix(var.edge.certificate_vault_id, "/") }] : [],
  )
}

output "central_rbac_handoff" {
  description = "Central-owned grant requests with actual managed identity principal IDs; not grant verification or runtime approval. Export after resource provisioning."
  value = {
    owner                 = "central-team-external"
    runtime_gate_attested = var.manual_rbac_verified
    assignments = [for request in local.central_grant_requests : merge(request, {
      principal_id       = azurerm_user_assigned_identity.identity[request.identity].principal_id
      role_definition_id = "/subscriptions/${var.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/${local.central_builtin_roles[request.role]}"
      status             = "request-only-not-verified"
    })]
    custom_role_requests = concat([
      {
        name             = "${local.prefix}-subscription-manager"
        principal_id     = try(azurerm_user_assigned_identity.identity["api"].principal_id, null)
        assignment_scope = local.central_apim_scope
        assignable_scope = local.rg_id
        actions = [
          "Microsoft.ApiManagement/service/read",
          "Microsoft.ApiManagement/service/products/read",
          "Microsoft.ApiManagement/service/subscriptions/read",
          "Microsoft.ApiManagement/service/subscriptions/write",
          "Microsoft.ApiManagement/service/subscriptions/listSecrets/action",
          "Microsoft.ApiManagement/service/subscriptions/regeneratePrimaryKey/action",
          "Microsoft.ApiManagement/service/subscriptions/regenerateSecondaryKey/action",
        ]
      }
      ], [for scope in local.gateway_settings_scopes : {
        name             = "${local.prefix}-gateway-settings"
        principal_id     = azurerm_user_assigned_identity.identity["api"].principal_id
        assignment_scope = "${local.central_apim_scope}/policyFragments/aiflux-${scope}-settings"
        assignable_scope = local.rg_id
        actions          = ["Microsoft.ApiManagement/service/policyFragments/read", "Microsoft.ApiManagement/service/policyFragments/write"]
    }])
    database_bootstrap = {
      scope = "${local.rg_id}/providers/Microsoft.DBforPostgreSQL/flexibleServers/${local.prefix}-pg/databases/turnstile"
      identities = { for name in ["api", "ingestion", "control-plane"] : name => {
        principal_id = try(azurerm_user_assigned_identity.identity[name].principal_id, null)
        login        = "${local.prefix}-${name}-identity"
      } }
      status = "Separate private PostgreSQL Entra principal/schema grants, not Azure RBAC; pending database administrator execution."
    }
  }
}