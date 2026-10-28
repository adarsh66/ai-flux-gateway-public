mock_provider "azapi" {}
mock_provider "azurerm" {}

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

run "external_is_disabled_and_unadvertised_by_default" {
  command = plan
  assert {
    condition     = length(azapi_resource.glm_backend) == 0 && length(azapi_resource.glm_named_value) == 0 && !strcontains(local.policy, "glm-5.3")
    error_message = "A pending external provider must not create resources or appear in /models."
  }
}

run "external_render_preserves_persistent_guards" {
  command = plan
  variables {
    glm_enabled               = true
    persistent_poc_authorized = true
    demo_authorized           = true
    daily_call_allowance      = 1000
    rpm_limit                 = 60
    tpm_limit                 = 2048
    completion_token_limit    = 1024
  }
  assert {
    condition     = strcontains(local.policy, "Bearer {{aiflux-glm-5-3-api-key}}") && !strcontains(local.policy, "context.NamedValues") && !strcontains(local.policy, "<retry") && length(regexall("<forward-request", local.policy)) == 1 && length(regexall("<llm-content-safety", local.policy)) == 3
    error_message = "External dispatch must retain mandatory guardrails and correct named-value substitution."
  }
  assert {
    condition     = strcontains(local.policy, "project-demo:") && strcontains(local.policy, "token-quota=\"10000\"") && !strcontains(local.policy, "first-period-start") && !strcontains(local.policy, "demo_expired")
    error_message = "External opt-in must never reset counters, raise quotas or restore expiry."
  }
}

run "external_reference_rejects_version_or_arbitrary_secret" {
  command = plan
  variables {
    glm_secret_identifier = "https://pocidstokenexkv.vault.azure.net/secrets/glm-5-3-api-key/version"
  }
  expect_failures = [var.glm_secret_identifier]
}

run "internal_secret_is_never_terraform_owned" {
  command = plan
  variables {
    enabled                      = true
    glm_enabled                  = true
    glm_credential_storage       = "apim-internal"
    glm_internal_secret_verified = true
    persistent_poc_authorized    = true
    demo_authorized              = true
    daily_call_allowance         = 1000
    rpm_limit                    = 60
    tpm_limit                    = 2048
    completion_token_limit       = 1024
  }
  assert {
    condition     = length(azapi_resource.glm_named_value) == 0 && length(azapi_resource.glm_backend) == 1
    error_message = "Internal secret must pre-exist outside Terraform; only its backend may be created."
  }
}

run "internal_secret_missing_metadata_blocks_route" {
  command = plan
  variables {
    enabled                   = true
    glm_enabled               = true
    persistent_poc_authorized = true
    demo_authorized           = true
    daily_call_allowance      = 1000
    rpm_limit                 = 60
    tpm_limit                 = 2048
    completion_token_limit    = 1024
  }
  expect_failures = [azapi_resource.glm_backend]
}

run "internal_secret_cannot_silently_use_vault_resolver" {
  command = plan
  variables {
    enabled                      = true
    glm_enabled                  = true
    glm_internal_secret_verified = true
    glm_resolver_verified        = true
    persistent_poc_authorized    = true
    demo_authorized              = true
    daily_call_allowance         = 1000
    rpm_limit                    = 60
    tpm_limit                    = 2048
    completion_token_limit       = 1024
  }
  expect_failures = [azapi_resource.glm_backend]
}

run "explicit_key_vault_reference_remains_optional" {
  command = plan
  variables {
    enabled                   = true
    glm_enabled               = true
    glm_credential_storage    = "key-vault"
    glm_resolver_verified     = true
    glm_secret_identifier     = "https://pocidstokenexkv.vault.azure.net/secrets/glm-5-3-api-key"
    persistent_poc_authorized = true
    demo_authorized           = true
    daily_call_allowance      = 1000
    rpm_limit                 = 60
    tpm_limit                 = 2048
    completion_token_limit    = 1024
  }
  assert {
    condition     = length(azapi_resource.glm_named_value) == 1
    error_message = "Only explicit verified Key Vault mode may own a vault reference."
  }
}
