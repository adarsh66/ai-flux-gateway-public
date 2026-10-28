mock_provider "azapi" {}
mock_provider "azurerm" {}

run "defaults_have_no_cloud_changes_or_accepted_route" {
  command = plan
  assert {
    condition     = length(azapi_resource.project_child) == 0 && length(azapi_resource.project_policy) == 0 && length(azapi_resource.project_global_gate) == 0
    error_message = "Conservative configuration alone must not create or activate any APIM resource."
  }
  assert {
    condition     = var.safety_threshold == 1 && !var.acceptance_verified && !var.candidate_validation && !var.allow_product_subscriptions
    error_message = "The authorized usable default is not a passing acceptance record."
  }
  assert {
    condition     = var.rpm_limit == 1 && var.rate_limit_window_seconds == 60 && var.tpm_limit == 1000 && var.daily_token_quota == 10000 && var.daily_call_allowance == 8 && var.completion_token_limit == 32 && var.backend_retries == 0
    error_message = "The bounded profile must keep its explicitly reviewed defaults."
  }
  assert {
    condition     = local.project_endpoint == "https://poc-ids-token-ex-foundry.services.ai.azure.com/api/projects/poc-ids-token-ex-foundry-project"
    error_message = "The superseded project must never return."
  }
}

run "zero_threshold_cannot_be_attested_usable" {
  command = plan
  variables {
    enabled             = true
    acceptance_verified = true
    safety_threshold    = 0
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
  expect_failures = [azapi_resource.project_child]
}

run "invalid_rpm_window_is_rejected_without_activation" {
  command = plan
  variables {
    rate_limit_window_seconds = 301
  }
  expect_failures = [var.rate_limit_window_seconds]
}

run "retries_are_rejected_even_when_disabled" {
  command = plan
  variables {
    backend_retries = 1
  }
  expect_failures = [var.backend_retries]
}

run "daily_quota_cannot_be_smaller_than_minute_limit" {
  command = plan
  variables {
    daily_token_quota = 999
  }
  expect_failures = [var.daily_token_quota]
}

run "unlimited_daily_calls_are_rejected" {
  command = plan
  variables {
    daily_call_allowance = 0
  }
  expect_failures = [var.daily_call_allowance]
}

run "candidate_cannot_inherit_demo_call_increase" {
  command = plan
  variables {
    candidate_validation = true
    daily_call_allowance = 1000
  }
  assert {
    condition     = strcontains(local.policy, "calls=\"8\" renewal-period=\"86400\"") && strcontains(local.policy, "project-validation:")
    error_message = "Only the final demo can receive a separate authorized allowance; candidate stays eight."
  }
}

run "authorized_demo_preserves_quota_identity_and_epoch" {
  command = plan
  variables {
    demo_authorized      = true
    daily_call_allowance = 1000
    rpm_limit            = 60
    demo_expires_at      = "2026-10-27T05:41:01Z"
  }
  assert {
    condition     = strcontains(local.policy, "calls=\"1000\" renewal-period=\"86400\"") && strcontains(local.policy, "project-demo:") && !strcontains(local.policy, "first-period-start") && strcontains(local.policy, "token-quota=\"10000\"")
    error_message = "Call increase must not alter counter identity, epoch, or token quota."
  }
}

run "explicit_persistent_poc_has_no_deadline_and_bounded_output" {
  command = plan
  variables {
    persistent_poc_authorized = true
    demo_authorized           = true
    daily_call_allowance      = 1000
    rpm_limit                 = 60
    tpm_limit                 = 2048
    completion_token_limit    = 1024
  }
  assert {
    condition     = !strcontains(local.policy, "demo_expired") && !strcontains(local.policy, "DateTime.Parse") && strcontains(local.policy, "modelMaximum = 1024;") && strcontains(local.policy, "tokens-per-minute=\"2048\"") && strcontains(local.policy, "token-quota=\"10000\"") && strcontains(local.policy, "project-demo:") && !strcontains(local.policy, "first-period-start")
    error_message = "Persistent POC must remove the deadline without loosening daily quota or resetting counters."
  }
}

run "persistent_poc_rejects_quota_loosening" {
  command = plan
  variables {
    persistent_poc_authorized = true
    demo_authorized           = true
    daily_call_allowance      = 1000
    rpm_limit                 = 60
    tpm_limit                 = 2048
    completion_token_limit    = 1024
    daily_token_quota         = 10001
  }
  expect_failures = [var.persistent_poc_authorized]
}

run "output1024_requires_explicit_persistent_authorization" {
  command = plan
  variables {
    completion_token_limit = 1024
    tpm_limit              = 2048
  }
  expect_failures = [var.persistent_poc_authorized]
}

run "explicit_product_poc_preserves_auth_and_all_limits" {
  command = plan
  variables {
    allow_product_subscriptions = true
    persistent_poc_authorized   = true
    demo_authorized             = true
    daily_call_allowance        = 1000
    rpm_limit                   = 60
    tpm_limit                   = 2048
    completion_token_limit      = 1024
  }
  assert {
    condition     = strcontains(local.policy, "context.Subscription == null || context.Product == null || context.Product.Id != \"aiflux\"") && !strcontains(local.policy, "context.Subscription.Id !=") && strcontains(local.policy, "project-demo:") && strcontains(local.policy, "token-quota=\"10000\"") && !strcontains(local.policy, "first-period-start") && !strcontains(local.policy, "<retry")
    error_message = "Only the original subscriber predicate may disappear; product/key authentication and stable bounded counters remain."
  }
}

run "product_optin_without_persistent_poc_is_rejected" {
  command = plan
  variables {
    allow_product_subscriptions = true
  }
  expect_failures = [var.allow_product_subscriptions]
}

run "product_optin_cannot_open_candidate" {
  command = plan
  variables {
    allow_product_subscriptions = true
    candidate_validation        = true
  }
  expect_failures = [var.allow_product_subscriptions]
}

run "product_optin_cannot_open_production_acceptance" {
  command = plan
  variables {
    allow_product_subscriptions = true
    acceptance_verified         = true
  }
  expect_failures = [var.allow_product_subscriptions]
}

run "candidate_retains_original_subscriber" {
  command = plan
  variables {
    candidate_validation = true
  }
  assert {
    condition     = strcontains(local.policy, "context.Subscription.Id != \"${local.subscriber}\"") && local.api_name == "aiflux-project-validation"
    error_message = "Candidate validation must retain its original subscriber restriction."
  }
}
