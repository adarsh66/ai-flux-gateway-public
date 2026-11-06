# Exact existing Fireworks deployments only. No roles, secrets or model writes.
locals {
  # Both profiles retain persistent exact-product authentication. Scoped
  # controls are compatible only with the reviewed complete thirteen-model
  # envelope and the existing, verified runtime-owned fragment; never candidate,
  # production acceptance, partial catalog or an unverified publisher profile.
  fireworks_poc_aliases = toset([
    "gpt-5.6-luna", "gpt-6.1-sol", "gpt-5.4-mini", "gpt-4o",
    "DeepSeek-V4-Flash", "DeepSeek-V4-Pro", "Kimi-K2.7-Code", "grok-4.3",
    "grok-4-20-reasoning", "grok-4-1-fast-reasoning", "FW-GLM-5.3", "FW-MiniMax-M3", "glm-5.3"
  ])
  fireworks_profile_compatible = (
    var.persistent_poc_authorized && var.glm_enabled && var.allow_product_subscriptions &&
    !var.candidate_validation && !var.acceptance_verified &&
    (!var.poc_controls_enabled || (
      var.poc_settings_bootstrap_enabled && var.poc_publisher_permissions_verified &&
      toset(local.all_aliases) == local.fireworks_poc_aliases &&
      toset(local.fireworks_aliases) == toset(keys(local.fireworks_contracts)) &&
      alltrue([for alias in local.fireworks_aliases :
        local.routes[alias].provider == "Fireworks" &&
        local.routes[alias].version == local.fireworks_contracts[alias].version &&
        try(local.routes[alias].upstream_url, "") == local.fireworks_url &&
        local.route_backends[alias] == local.fireworks_backend
      ])
    ))
  )
}

resource "azapi_resource" "fireworks_backend" {
  count     = var.enabled && length(local.fireworks_aliases) > 0 ? 1 : 0
  type      = "Microsoft.ApiManagement/service/backends@2024-05-01"
  parent_id = local.apim
  name      = local.fireworks_backend
  body = { properties = {
    protocol = "http", url = local.fireworks_url
    tls      = { validateCertificateChain = true, validateCertificateName = true }
  } }
  lifecycle {
    precondition {
      condition     = local.fireworks_profile_compatible
      error_message = "Fireworks requires persistent exact-product POC access with external GLM; scoped controls additionally require the complete reviewed thirteen-model routes and an existing fragment with verified publisher permissions. Candidate, acceptance and partial profiles are forbidden."
    }
  }
}