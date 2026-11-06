# Explicit successor, not a relaxation of the historical exact-eight profile.
# Reuses both existing native backends at their SAME Terraform addresses.
locals {
  successor22_manifest_path = abspath("${path.module}/../../gateway/catalog/foundry-successor22-candidate-routes.json")
  successor22_enabled       = var.route_manifest_path != "" && abspath(var.route_manifest_path) == local.successor22_manifest_path
  successor22_predecessor   = jsondecode(file(local.foundry_eight_manifest_path))
  successor22_ninth = {
    "mistral-medium-3-5" = { model_name = "mistral-medium-3-5", version = "1", provider = "Mistral AI", sku = "GlobalStandard", capacity = 5000, token_parameter = "max_tokens", upstream_url = local.foundry_eight_mistral_url, api_format = "openai-chat-completions" }
  }
  successor22_manifest_valid = local.successor22_enabled ? try(
    var.persistent_poc_authorized && var.allow_product_subscriptions && var.glm_enabled &&
    (!var.auto_routing_enabled || local.auto_release_validation_satisfied) && !var.poc_controls_enabled && length(var.excluded_routes) == 0 &&
    jsonencode({ for k, v in local.route_manifest : k => v if k != "routes" }) == jsonencode({ for k, v in local.successor22_predecessor : k => v if k != "routes" }) &&
    jsonencode(local.routes) == jsonencode(merge(local.successor22_predecessor.routes, local.successor22_ninth)), false
  ) : true
  successor22_deployment_ready = !local.successor22_enabled || !var.enabled ? true : try(
    data.azapi_resource.route_deployment["mistral-medium-3-5"].output.properties.provisioningState == "Succeeded" &&
    data.azapi_resource.route_deployment["mistral-medium-3-5"].output.properties.model.name == "mistral-medium-3-5" &&
    data.azapi_resource.route_deployment["mistral-medium-3-5"].output.properties.model.version == "1" &&
    data.azapi_resource.route_deployment["mistral-medium-3-5"].output.properties.model.format == "Mistral AI" &&
    data.azapi_resource.route_deployment["mistral-medium-3-5"].output.sku.name == "GlobalStandard" &&
    data.azapi_resource.route_deployment["mistral-medium-3-5"].output.sku.capacity == 5000 &&
    data.azapi_resource.route_deployment["mistral-medium-3-5"].output.properties.currentCapacity == 5000 &&
    data.azapi_resource.route_deployment["mistral-medium-3-5"].output.properties.raiPolicyName == "Microsoft.DefaultV2" &&
    data.azapi_resource.route_deployment["mistral-medium-3-5"].output.properties.capabilities.chatCompletion == "true" &&
    contains(["Active", "Succeeded"], coalesce(try(data.azapi_resource.route_deployment["mistral-medium-3-5"].output.properties.deploymentState, null), "Active")), false
  )
  native_profile_enabled = local.foundry_eight_enabled || local.successor22_enabled
  native_manifest_valid  = local.successor22_enabled ? local.successor22_manifest_valid && local.successor22_deployment_ready : local.foundry_eight_manifest_valid
}