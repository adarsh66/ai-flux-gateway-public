# Source-only opt-in for eight EXISTING deployments. No model, role, identity,
# settings or secret provisioning. Historical manifests remain release inputs.
locals {
  foundry_eight_manifest_path     = abspath("${path.module}/../../gateway/catalog/foundry-eight-candidate-routes.json")
  foundry_eight_enabled           = var.route_manifest_path != "" && abspath(var.route_manifest_path) == local.foundry_eight_manifest_path
  foundry_eight_original          = jsondecode(file("${path.module}/../../gateway/catalog/fireworks-candidate-routes.json"))
  foundry_eight_anthropic_url     = "https://poc-ids-token-ex-foundry.services.ai.azure.com/anthropic/v1"
  foundry_eight_mistral_url       = "https://poc-ids-token-ex-foundry.services.ai.azure.com/openai/v1"
  foundry_eight_anthropic_backend = "aiflux-project-foundry-eight-anthropic"
  foundry_eight_mistral_backend   = "aiflux-project-foundry-eight-mistral"

  # Exact properties.model.name, version, format and SKU from BOTH retained
  # requested.json and deployments.json. Fast really has its own model name.
  # All five Claude records actually advertise chatCompletion=true; an absent
  # or false flag is NOT evidence to waive readiness for these deployments.
  foundry_eight_contracts = {
    "claude-sonnet-5-5"    = { model_name = "claude-sonnet-5-5", version = "2", provider = "Anthropic", sku = "GlobalStandard", capacity = 5000, token_parameter = "max_tokens", upstream_url = local.foundry_eight_anthropic_url, api_format = "anthropic-messages" }
    "claude-opus-5-5"      = { model_name = "claude-opus-5-5", version = "2", provider = "Anthropic", sku = "GlobalStandard", capacity = 5000, token_parameter = "max_tokens", upstream_url = local.foundry_eight_anthropic_url, api_format = "anthropic-messages" }
    "claude-opus-5-5-fast" = { model_name = "claude-opus-5-5-fast", version = "2", provider = "Anthropic", sku = "GlobalStandard", capacity = 2000, token_parameter = "max_tokens", upstream_url = local.foundry_eight_anthropic_url, api_format = "anthropic-messages" }
    "claude-haiku-5-5"     = { model_name = "claude-haiku-5-5", version = "2", provider = "Anthropic", sku = "GlobalStandard", capacity = 5000, token_parameter = "max_tokens", upstream_url = local.foundry_eight_anthropic_url, api_format = "anthropic-messages" }
    "claude-opus-4-8"      = { model_name = "claude-opus-4-8", version = "2", provider = "Anthropic", sku = "GlobalStandard", capacity = 5000, token_parameter = "max_tokens", upstream_url = local.foundry_eight_anthropic_url, api_format = "anthropic-messages" }
    "gpt-6.1-terra"        = { model_name = "gpt-6.1-terra", version = "2026-10-26", provider = "OpenAI", sku = "GlobalStandard", capacity = 5000, token_parameter = "max_completion_tokens", upstream_url = local.foundry_eight_original.upstream_url, api_format = "openai-chat-completions" }
    "gpt-6-luna"           = { model_name = "gpt-6-luna", version = "2026-09-22", provider = "OpenAI", sku = "GlobalStandard", capacity = 5000, token_parameter = "max_completion_tokens", upstream_url = local.foundry_eight_original.upstream_url, api_format = "openai-chat-completions" }
    "Mistral-Large-3"      = { model_name = "Mistral-Large-3", version = "1", provider = "Mistral AI", sku = "GlobalStandard", capacity = 5000, token_parameter = "max_tokens", upstream_url = local.foundry_eight_mistral_url, api_format = "openai-chat-completions" }
  }
  foundry_eight_anthropic_aliases  = local.native_profile_enabled ? sort([for alias, route in local.foundry_eight_contracts : alias if route.provider == "Anthropic"]) : []
  foundry_eight_alias_conditions   = length(local.foundry_eight_anthropic_aliases) == 0 ? "false" : join(" || ", [for alias in local.foundry_eight_anthropic_aliases : "(string)model == \"${alias}\""])
  foundry_eight_context_conditions = length(local.foundry_eight_anthropic_aliases) == 0 ? "false" : join(" || ", [for alias in local.foundry_eight_anthropic_aliases : "(string)context.Variables[\"aiflux-model\"] == \"${alias}\""])
  foundry_eight_manifest_valid = local.foundry_eight_enabled ? try(
    var.persistent_poc_authorized && var.allow_product_subscriptions && var.glm_enabled &&
    # These are APIM route inputs, NOT the API's retained runtime settings.
    # Actual active policy has no include-fragment. Keeping this false preserves
    # that behavior; enabling it would attach controls, not preserve controls.
    !var.auto_routing_enabled && !var.poc_controls_enabled &&
    length(var.excluded_routes) == 0 &&
    local.route_manifest.schema_version == 1 &&
    local.route_manifest.project_endpoint == local.foundry_eight_original.project_endpoint &&
    local.route_manifest.upstream_url == local.foundry_eight_original.upstream_url &&
    local.route_manifest.gateway_url == local.foundry_eight_original.gateway_url &&
    jsonencode(local.routes) == jsonencode(merge(local.foundry_eight_original.routes, local.foundry_eight_contracts)), false
  ) : local.successor22_enabled ? false : length(setintersection(toset(keys(local.routes)), toset(keys(local.foundry_eight_contracts)))) == 0
  foundry_eight_deployments_ready = !local.native_profile_enabled || !var.enabled ? true : alltrue([
    for alias, route in local.foundry_eight_contracts : try(
      data.azapi_resource.route_deployment[alias].output.properties.provisioningState == "Succeeded" &&
      data.azapi_resource.route_deployment[alias].output.properties.model.name == route.model_name &&
      data.azapi_resource.route_deployment[alias].output.properties.model.version == route.version &&
      data.azapi_resource.route_deployment[alias].output.properties.model.format == route.provider &&
      data.azapi_resource.route_deployment[alias].output.sku.name == route.sku &&
      data.azapi_resource.route_deployment[alias].output.sku.capacity == route.capacity &&
      data.azapi_resource.route_deployment[alias].output.properties.currentCapacity == route.capacity &&
      data.azapi_resource.route_deployment[alias].output.properties.raiPolicyName == "Microsoft.DefaultV2" &&
      data.azapi_resource.route_deployment[alias].output.properties.capabilities.chatCompletion == "true" &&
      contains(["Active", "Succeeded"], coalesce(try(data.azapi_resource.route_deployment[alias].output.properties.deploymentState, null), "Active")), false
    )
  ])

  # external.tf intentionally owns the original Fireworks/GLM authentication
  # rewrite. Compose AFTER it, never change the historical anchor or its input.
  # Native version is restored AFTER caller-header deletion, only for Claude.
  foundry_eight_native_auth    = <<-XML
      <when condition='@(${local.foundry_eight_context_conditions})'>
        <set-header name="anthropic-version" exists-action="override"><value>2023-06-01</value></set-header>
        <authentication-managed-identity resource="https://ai.azure.com" client-id="${local.gateway_client}" ignore-error="false" />
      </when>
  XML
  foundry_eight_auth           = replace(local.glm_auth, "<otherwise><authentication-managed-identity", "${local.foundry_eight_native_auth}<otherwise><authentication-managed-identity")
  foundry_eight_base_policy    = var.poc_controls_enabled ? local.poc_policy : local.auto_policy
  foundry_eight_clean_headers  = join("", [for header in ["anthropic-beta", "x-ms-api-key", "x-ms-authorization-auxiliary", "x-aiflux-provider", "x-aiflux-speed", "x-ms-model-deployment", "x-ms-model-name", "x-ms-model-version"] : "<set-header name=\"${header}\" exists-action=\"delete\" />"])
  foundry_eight_inbound        = replace(local.foundry_eight_base_policy, local.glm_auth, "${local.foundry_eight_clean_headers}${local.foundry_eight_auth}")
  foundry_eight_response_guard = <<-XML
    <choose><when condition='@(${local.foundry_eight_context_conditions})'>
      <set-header name="Location" exists-action="delete" />
      <set-header name="Set-Cookie" exists-action="delete" />
      <set-header name="WWW-Authenticate" exists-action="delete" />
      <set-header name="Authorization" exists-action="delete" />
      <set-header name="api-key" exists-action="delete" />
      <set-header name="x-api-key" exists-action="delete" />
      <choose><when condition='@(context.Response.StatusCode != 200)'>
        <return-response>
          <set-status code='@(context.Response.StatusCode == 429 ? 429 : 503)' reason="Model request unavailable" />
          ${local.error_cors}
          <set-header name="Content-Type" exists-action="override"><value>application/json</value></set-header>
          <set-header name="Cache-Control" exists-action="override"><value>no-store</value></set-header>
          <set-header name="Retry-After" exists-action="override"><value>60</value></set-header>
          <set-body>{"error":{"code":"native_model_unavailable","message":"The model request was not completed; no fallback or retry was attempted."}}</set-body>
        </return-response>
      </when></choose>
    </when></choose>
  XML
  foundry_eight_response_final = <<-XML
    <choose><when condition='@(${local.foundry_eight_context_conditions})'>
      <!-- Fresh response only AFTER strict normalization and output safety. -->
      <set-variable name="aiflux-native-answer" value='@(context.Response.Body.As&lt;string&gt;(preserveContent: true))' />
      <return-response><set-status code="200" reason="OK" />
        ${local.error_cors}
        <set-header name="Content-Type" exists-action="override"><value>application/json</value></set-header>
        <set-header name="Cache-Control" exists-action="override"><value>no-store</value></set-header>
        <set-header name="x-aiflux-request-id" exists-action="override"><value>@(context.RequestId.ToString())</value></set-header>
        <set-body>@((string)context.Variables["aiflux-native-answer"])</set-body>
      </return-response>
    </when></choose>
  XML
  foundry_eight_outbound       = replace(local.foundry_eight_inbound, "<outbound>\n    <base />", "<outbound>\n    <base />${local.foundry_eight_response_guard}")
  foundry_eight_policy         = local.native_profile_enabled ? replace(local.foundry_eight_outbound, "</outbound>", "${local.foundry_eight_response_final}</outbound>") : local.foundry_eight_base_policy
}

resource "azapi_resource" "foundry_eight_backend" {
  for_each = var.enabled && local.native_profile_enabled ? {
    anthropic = { name = local.foundry_eight_anthropic_backend, url = local.foundry_eight_anthropic_url }
    mistral   = { name = local.foundry_eight_mistral_backend, url = local.foundry_eight_mistral_url }
  } : {}
  type      = "Microsoft.ApiManagement/service/backends@2024-05-01"
  parent_id = local.apim
  name      = each.value.name
  body = { properties = {
    protocol = "http", url = each.value.url
    tls      = { validateCertificateChain = true, validateCertificateName = true }
  } }
  lifecycle {
    precondition {
      condition     = local.native_manifest_valid
      error_message = "Only the exact opt-in twenty-route additive manifest may create these APIM child backends."
    }
    precondition {
      condition     = local.foundry_eight_deployments_ready
      error_message = "All eight existing ARM deployments must match the retained exact readiness contracts before adding either APIM backend."
    }
    precondition {
      condition = (
        length(split(local.glm_auth, local.foundry_eight_base_policy)) == 2 &&
        length(split(local.foundry_eight_native_auth, local.foundry_eight_policy)) == 2 &&
        length(split(local.foundry_eight_response_guard, local.foundry_eight_policy)) == 2 &&
        !strcontains(local.policy, "<retry") && length(regexall("<forward-request", local.policy)) == 1
      )
      error_message = "Native authentication composition must match once, retain GLM/Fireworks auth and never introduce retries."
    }
  }
}