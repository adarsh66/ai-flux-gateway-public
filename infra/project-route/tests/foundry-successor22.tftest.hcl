# Offline successor-only contracts. Provider overrides are inherited by the
# isolated runner from the unchanged historical suite; no live acceptance.
mock_provider "azapi" {}
mock_provider "azurerm" {}

variables {
  route_manifest_path          = "../../gateway/catalog/foundry-successor22-candidate-routes.json"
  persistent_poc_authorized    = true
  demo_authorized              = true
  allow_product_subscriptions  = true
  glm_enabled                  = true
  glm_internal_secret_verified = true
  rpm_limit                    = 60
  tpm_limit                    = 2048
  daily_call_allowance         = 1000
  completion_token_limit       = 1024
}

override_data {
  target = data.azapi_resource.route_deployment["mistral-medium-3-5"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 5000 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
      model             = { format = "Mistral AI", name = "mistral-medium-3-5", version = "1" }
      capabilities      = { chatCompletion = "true" }
    }
  } }
}

run "explicit_successor_exact22_old21_contracts" {
  command = plan
  assert {
    condition = (
      local.successor22_enabled && local.successor22_manifest_valid && local.native_manifest_valid &&
      !local.foundry_eight_enabled && !local.foundry_eight_manifest_valid &&
      toset(keys(local.routes)) == setunion(toset(keys(local.successor22_predecessor.routes)), toset(["mistral-medium-3-5"])) &&
      toset(local.all_aliases) == setunion(toset(keys(local.successor22_predecessor.routes)), toset(["glm-5.3", "mistral-medium-3-5"])) &&
      alltrue([for alias, route in local.successor22_predecessor.routes : jsonencode(local.routes[alias]) == jsonencode(route)]) &&
      !contains(local.all_aliases, "Decision-1") && !contains(local.all_aliases, "auto")
    )
    error_message = "Exact original21+ninth only; historical exact8 remains distinct and rejects successor."
  }
  assert {
    condition = (
      local.route_backends["mistral-medium-3-5"] == "aiflux-project-foundry-eight-mistral" &&
      local.route_backends["Mistral-Large-3"] == "aiflux-project-foundry-eight-mistral" &&
      length(local.foundry_eight_anthropic_aliases) == 5 &&
      strcontains(local.policy, "request.Remove(\"max_completion_tokens\")") &&
      !strcontains(local.policy, "<retry") && length(regexall("<forward-request", local.policy)) == 1
    )
    error_message = "Reuse existing native backend, token conversion, Claude guards and retry0."
  }
}

run "enabled_successor_reuses_exact_existing_backend_addresses" {
  command = plan
  variables { enabled = true }
  assert {
    condition = (
      local.successor22_deployment_ready && local.foundry_eight_deployments_ready &&
      toset(keys(azapi_resource.foundry_eight_backend)) == toset(["anthropic", "mistral"]) &&
      azapi_resource.foundry_eight_backend["mistral"].name == "aiflux-project-foundry-eight-mistral" &&
      azapi_resource.foundry_eight_backend["mistral"].body.properties.url == local.foundry_eight_mistral_url
    )
    error_message = "No successor backend/resource address may be introduced."
  }
}

run "successor_partial_manifest_rejected" {
  command = plan
  variables { excluded_routes = ["mistral-medium-3-5"] }
  assert {
    condition     = !local.successor22_manifest_valid && !local.native_manifest_valid
    error_message = "No partial successor or count-based acceptance."
  }
}

run "historical_profile_still_excludes_ninth" {
  command = plan
  variables { route_manifest_path = "../../gateway/catalog/foundry-eight-candidate-routes.json" }
  assert {
    condition = (
      local.foundry_eight_enabled && local.foundry_eight_manifest_valid && !local.successor22_enabled &&
      !contains(local.all_aliases, "mistral-medium-3-5") &&
      toset(keys(local.routes)) == toset(keys(local.successor22_predecessor.routes))
    )
    error_message = "Historical exact-eight profile must remain exact and opt-in."
  }
}