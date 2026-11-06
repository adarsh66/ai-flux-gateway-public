# Mock-only tests: no backend, remote data reads, inference or deployment.
mock_provider "azapi" {}
mock_provider "azurerm" {}

variables {
  enabled                        = false
  poc_settings_bootstrap_enabled = false
}

run "auto_off_is_exact_identity" {
  command = plan
  assert {
    condition     = !var.auto_routing_enabled && var.auto_routing_runtime_evidence_sha256 == "" && !var.admin_settings_enabled
    error_message = "Auto must default off with no implicit endpoint or token resource."
  }
  assert {
    condition     = local.auto_policy == local.glm_policy && !strcontains(local.policy, "aiflux-auto")
    error_message = "Off must preserve original bytes without whitespace, headers or routing-profile acceptance."
  }
  assert {
    condition     = length(azapi_resource.project_child) == 0 && length(azapi_resource.project_policy) == 0 && length(azapi_resource.project_global_gate) == 0 && length(azapi_resource.poc_settings) == 0
    error_message = "Auto adds no resources and defaults must not create existing ones."
  }
}

run "render_source_only_auto_composition" {
  command = plan
  variables {
    persistent_poc_authorized   = true
    demo_authorized             = true
    allow_product_subscriptions = true
    daily_call_allowance        = 1000
    rpm_limit                   = 60
    tpm_limit                   = 2048
    completion_token_limit      = 1024
  }
  assert {
    condition     = length(regexall("<quota-by-key", local.auto_with_error)) == 1 && length(regexall("auto-admission:", local.auto_with_error)) == 1
    error_message = "Shared daily call counter and Auto admission must occur once, not once per candidate or selected limit."
  }
  assert {
    condition     = length(regexall("shield-prompt=\"true\"", local.auto_with_error)) == 2 && length(regexall("window-size=\"1000\"", local.auto_with_error)) == 1 && length(regexall("id=\"aiflux-auto-resolver\"", local.auto_with_error)) == 1
    error_message = "Keep original, redacted and output safety with exactly one selection call."
  }
  assert {
    condition     = length(regexall("counter-key='@\\(\"rpm:", local.auto_with_error)) == 2 && length(regexall("counter-key='@\\(\"tpm:", local.auto_with_error)) == 2
    error_message = "Original explicit limits and mutually exclusive Auto selected limits must preserve exact counter keys."
  }
  assert {
    condition     = strcontains(local.auto_with_error, "aiflux-auto-auth\" resource=\"https://cognitiveservices.azure.com\" client-id=\"${local.gateway_client}\"") && !strcontains(local.auto_with_error, "/internal/auto-routing/resolve") && strcontains(local.auto_with_error, "request.Remove(\"routing_profile\")")
    error_message = "Only gateway MI may score at fixed Cognitive Services endpoint; no private API resolver dependency."
  }
  assert {
    condition     = local.auto_policy == local.glm_policy && length(local.auto_candidates) == 6 && !strcontains(local.auto_with_error, "set-backend-service backend-id=\"auto")
    error_message = "Candidate source rendering must not enable Auto or invent an Auto inference backend."
  }
}

run "auto_requires_poc_and_secure_existing_configuration" {
  command = plan
  variables {
    auto_routing_enabled = true
  }
  expect_failures = [var.auto_routing_enabled]
}

run "invalid_runtime_evidence_rejected_even_off" {
  command = plan
  variables {
    auto_routing_runtime_evidence_sha256 = "https://attacker.invalid/"
  }
  expect_failures = [var.auto_routing_runtime_evidence_sha256]
}

run "shared_defaults_are_source_bound_not_subscriber_ids" {
  command = plan
  assert {
    condition     = local.auto_inputs_bound && length(local.auto_profiles) == 3 && length(local.auto_profiles.balanced.candidate_models) == 6 && local.auto_profiles.cost.fallback_model == "gpt-5.4-mini"
    error_message = "All three default profiles must ship source-bound to accepted catalog and pricing."
  }
}

run "shared_pricing_inclusion_keeps_runtime_payload_detached" {
  command = plan
  assert {
    condition     = local.auto_arguments.pricing_fragment == local.poc_fragment_name && length(regexall("include-fragment fragment-id=\"${local.poc_fragment_name}\"", local.auto_with_error)) == 1
    error_message = "Reuse only the existing authorized runtime fragment, once in Auto's price-only branch."
  }
  assert {
    condition     = strcontains(local.auto_with_error, "name=\"aiflux-auto-price-only\" value=\"@(true)\"") && strcontains(local.auto_with_error, "name=\"aiflux-auto-price-only\" value=\"@(false)\"") && !var.poc_controls_enabled && !var.admin_settings_enabled
    error_message = "Pricing inclusion must reset its mode and cannot activate detached controls or quotas."
  }
  assert {
    condition     = local.auto_inputs_bound && length(local.auto_candidates) == 6 && length(local.auto_profiles) == 3
    error_message = "Mutable pricing must never change the immutable pool, profiles or manifest bindings."
  }
}

run "admin_fragment_incompatible" {
  command = plan
  variables {
    auto_routing_enabled   = true
    admin_settings_enabled = true
  }
  expect_failures = [var.auto_routing_enabled]
}

run "role_metadata_alone_cannot_activate_auto_even_in_poc" {
  command = plan
  variables {
    auto_routing_enabled        = true
    persistent_poc_authorized   = true
    demo_authorized             = true
    allow_product_subscriptions = true
    daily_call_allowance        = 1000
    rpm_limit                   = 60
    tpm_limit                   = 2048
    completion_token_limit      = 1024
  }
  expect_failures = [var.auto_routing_enabled]
}

run "direct_release_defaults_closed" {
  command = plan
  assert {
    condition     = var.auto_routing_direct_release == null && !local.auto_direct_release_valid
    error_message = "Direct production acceptance must never be inferred from default settings."
  }
}

run "unbounded_direct_release_rejected" {
  command = plan
  variables {
    auto_routing_direct_release = {
      mode                        = "bounded-production-direct-v1"
      defaults_sha256             = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      predecessor_sha256          = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      candidate_sha256            = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      independent_review_sha256   = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      rollback_sha256             = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      max_auto_attempts           = 3
      max_scoring_calls           = 2
      max_completion_calls        = 2
      retries                     = 0
      fallback                    = false
      runtime_validation_pending  = true
      stop_on_explicit_regression = true
    }
  }
  expect_failures = [var.auto_routing_direct_release]
}
