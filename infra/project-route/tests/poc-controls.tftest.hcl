mock_provider "azapi" {}
mock_provider "azurerm" {}

variables {
  persistent_poc_authorized   = true
  demo_authorized             = true
  allow_product_subscriptions = true
  daily_call_allowance        = 1000
  rpm_limit                   = 60
  tpm_limit                   = 2048
  completion_token_limit      = 1024
}

override_data {
  target = data.azapi_resource.deployment[0]
  values = {
    output = { properties = {
      provisioningState = "Succeeded", currentCapacity = 5000
      model             = { format = "OpenAI", name = "gpt-5.6-luna", version = "2026-07-09" }
      capabilities      = { chatCompletion = "true" }
    } }
  }
}

override_data {
  target = data.azapi_resource.project[0]
  values = {
    output = { properties = {
      provisioningState = "Succeeded"
      endpoints         = { "AI Foundry API" = "https://poc-ids-token-ex-foundry.services.ai.azure.com/api/projects/poc-ids-token-ex-foundry-project" }
    } }
  }
}

run "profile_is_off_by_default" {
  command = plan
  variables {
    enabled                        = true
    poc_settings_bootstrap_enabled = false
  }
  assert {
    condition     = !var.poc_controls_enabled && length(azapi_resource.poc_settings) == 0 && !strcontains(local.policy, "aiflux-dev-unified-poc-settings")
    error_message = "Existing persistent product policy must remain unchanged without explicit opt-in."
  }
}

run "bootstrap_creates_only_detached_safe_defaults_without_publisher_permission" {
  command = plan
  variables {
    enabled                            = true
    poc_settings_bootstrap_enabled     = true
    poc_controls_enabled               = false
    poc_publisher_permissions_verified = false
  }
  assert {
    condition     = length(azapi_resource.poc_settings) == 1 && !strcontains(local.policy, "<include-fragment") && local.attempt_policy == replace(local.glm_policy, "</inbound>", "<set-variable name=\"aiflux-backend-attempt\" value=\"@(1)\" /></inbound>")
    error_message = "Bootstrap creates the same-owner detached fragment, never changes the active policy or requires publisher permission."
  }
  assert {
    condition     = azapi_resource.poc_settings[0].name == "aiflux-dev-unified-poc-settings" && azapi_resource.poc_settings[0].body.properties.value == file("${path.module}/../../gateway/policies/poc-settings-defaults.xml")
    error_message = "Bootstrap must use exactly the reviewed safe-default XML, not an empty or runtime-generated fragment."
  }
}

run "disabled_parent_does_not_bootstrap" {
  command = plan
  variables {
    enabled                        = false
    poc_settings_bootstrap_enabled = true
  }
  assert {
    condition     = length(azapi_resource.poc_settings) == 0
    error_message = "Bootstrap may not bypass the parent enabled guard."
  }
}

run "bootstrap_does_not_bypass_activation_permission_guard" {
  command = plan
  variables {
    enabled                        = true
    poc_settings_bootstrap_enabled = true
    poc_controls_enabled           = true
  }
  expect_failures = [var.poc_controls_enabled]
}

run "missing_publisher_permission_refuses_activation" {
  command = plan
  variables {
    poc_controls_enabled = true
  }
  expect_failures = [var.poc_controls_enabled]
}

run "scoped_profile_preserves_auth_keys_windows_safety_and_dispatch" {
  command = plan
  variables {
    enabled                            = true
    poc_controls_enabled               = true
    poc_publisher_permissions_verified = true
    glm_enabled                        = true
    glm_internal_secret_verified       = true
  }
  assert {
    condition     = length(azapi_resource.poc_settings) == 1 && length(regexall("<include-fragment fragment-id=\"aiflux-dev-unified-poc-settings\"", local.policy)) == 1 && !strcontains(local.policy, "<quota-by-key") && strcontains(local.policy, "</include-fragment>") == false
    error_message = "One precreated fragment must replace precisely the existing call-quota position."
  }
  assert {
    condition     = strcontains(local.policy, "context.Subscription == null || context.Product == null || context.Product.Id != \"aiflux\"") && !strcontains(local.policy, "subscription_controls_unpublished") && !strcontains(local.policy, "aiflux:v2")
    error_message = "Optional controls cannot replace exact-product authentication or gate unknown membership."
  }
  assert {
    condition     = length(regexall("<rate-limit-by-key", local.policy)) == 1 && length(regexall("<llm-token-limit", local.policy)) == 1 && strcontains(local.policy, "rpm:") && strcontains(local.policy, "tpm:") && strcontains(local.policy, "renewal-period=\"60\"") && strcontains(local.policy, "token-quota-period=\"Daily\"") && !strcontains(local.policy, "first-period-start")
    error_message = "Counter keys, model scope, windows and singular policy execution must be preserved."
  }
  assert {
    condition     = length(regexall("aiflux-hate-threshold", local.policy)) == 3 && length(regexall("aiflux-violence-threshold", local.policy)) == 3 && length(regexall("aiflux-sexual-threshold", local.policy)) == 3 && length(regexall("aiflux-self-harm-threshold", local.policy)) == 3 && strcontains(local.policy, "pii_inspection_unavailable")
    error_message = "All categories must use the same effective threshold in all three mandatory safety passes."
  }
  assert {
    condition     = length(regexall("<forward-request", local.policy)) == 1 && !strcontains(local.policy, "<retry") && strcontains(local.policy, "glm-5.3") && strcontains(local.policy, "Bearer {{aiflux-glm-5-3-api-key}}") && strcontains(local.policy, "modelMaximum = 1024;")
    error_message = "GLM secret reference, dispatch, output bound and zero-retry behavior must not change."
  }
  assert {
    condition     = strcontains(azapi_resource.poc_settings[0].body.properties.value, "calls=\"1000\" renewal-period=\"86400\"") && strcontains(azapi_resource.poc_settings[0].body.properties.value, "project-demo:")
    error_message = "The default fragment must preserve the literal-call counter identity, period and ceiling."
  }
}