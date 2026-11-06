# Mock-only plan/render contracts. No live acceptance or inference claim.
mock_provider "azapi" {}
mock_provider "azurerm" {}

variables {
  route_manifest_path          = "../../gateway/catalog/foundry-eight-candidate-routes.json"
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
  target = data.azapi_resource.deployment[0]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 5000
    model             = { format = "OpenAI", name = "gpt-5.6-luna", version = "2026-07-09" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.project[0]
  values = { output = { properties = {
    provisioningState = "Succeeded"
    endpoints         = { "AI Foundry API" = "https://poc-ids-token-ex-foundry.services.ai.azure.com/api/projects/poc-ids-token-ex-foundry-project" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["gpt-5.6-luna"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 5000
    model             = { format = "OpenAI", name = "gpt-5.6-luna", version = "2026-07-09" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["gpt-6.1-sol"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 5000
    model             = { format = "OpenAI", name = "gpt-6.1-sol", version = "2026-09-29" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["gpt-5.4-mini"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 5000
    model             = { format = "OpenAI", name = "gpt-5.4-mini", version = "2026-03-17" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["gpt-4o"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 15000
    model             = { format = "OpenAI", name = "gpt-4o", version = "2024-11-20" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["DeepSeek-V4-Flash"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 2500
    model             = { format = "DeepSeek", name = "DeepSeek-V4-Flash", version = "2026-04-23" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["DeepSeek-V4-Pro"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 5000
    model             = { format = "DeepSeek", name = "DeepSeek-V4-Pro", version = "2026-04-23" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["Kimi-K2.7-Code"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 1000
    model             = { format = "MoonshotAI", name = "Kimi-K2.7-Code", version = "2026-06-12" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["grok-4.3"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 2500
    model             = { format = "xAI", name = "grok-4.3", version = "1" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["grok-4-20-reasoning"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 2500
    model             = { format = "xAI", name = "grok-4-20-reasoning", version = "1" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["grok-4-1-fast-reasoning"]
  values = { output = { properties = {
    provisioningState = "Succeeded", currentCapacity = 2500
    model             = { format = "xAI", name = "grok-4-1-fast-reasoning", version = "1" }
    capabilities      = { chatCompletion = "true" }
  } } }
}
override_data {
  target = data.azapi_resource.route_deployment["FW-GLM-5.3"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 250 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 250
      model             = { format = "Fireworks", name = "FW-GLM-5.3", version = "2" }
      capabilities      = { chatCompletion = "true" }
    }
  } }
}
override_data {
  target = data.azapi_resource.route_deployment["FW-MiniMax-M3"]
  values = { output = {
    sku = { name = "DataZoneStandard", capacity = 250 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 250
      model             = { format = "Fireworks", name = "FW-MiniMax-M3", version = "1" }
      capabilities      = { chatCompletion = "true" }
    }
  } }
}
override_data {
  target = data.azapi_resource.route_deployment["claude-sonnet-5-5"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 5000 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
      model             = { format = "Anthropic", name = "claude-sonnet-5-5", version = "2" }
      capabilities      = { agentsV2 = "true", chatCompletion = "true" }
    }
  } }
}
override_data {
  target = data.azapi_resource.route_deployment["claude-opus-5-5"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 5000 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
      model             = { format = "Anthropic", name = "claude-opus-5-5", version = "2" }
      capabilities      = { agentsV2 = "true", chatCompletion = "true" }
    }
  } }
}
override_data {
  target = data.azapi_resource.route_deployment["claude-opus-5-5-fast"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 2000 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 2000, raiPolicyName = "Microsoft.DefaultV2"
      model             = { format = "Anthropic", name = "claude-opus-5-5-fast", version = "2" }
      capabilities      = { agentsV2 = "true", chatCompletion = "true" }
    }
  } }
}
override_data {
  target = data.azapi_resource.route_deployment["claude-haiku-5-5"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 5000 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
      model             = { format = "Anthropic", name = "claude-haiku-5-5", version = "2" }
      capabilities      = { agentsV2 = "true", chatCompletion = "true" }
    }
  } }
}
override_data {
  target = data.azapi_resource.route_deployment["claude-opus-4-8"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 5000 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
      model             = { format = "Anthropic", name = "claude-opus-4-8", version = "2" }
      capabilities      = { agentsV2 = "true", chatCompletion = "true" }
    }
  } }
}
override_data {
  target = data.azapi_resource.route_deployment["gpt-6.1-terra"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 5000 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
      model             = { format = "OpenAI", name = "gpt-6.1-terra", version = "2026-10-26" }
      capabilities      = { chatCompletion = "true" }
    }
  } }
}
override_data {
  target = data.azapi_resource.route_deployment["gpt-6-luna"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 5000 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
      model             = { format = "OpenAI", name = "gpt-6-luna", version = "2026-09-22" }
      capabilities      = { chatCompletion = "true" }
    }
  } }
}
override_data {
  target = data.azapi_resource.route_deployment["Mistral-Large-3"]
  values = { output = {
    sku = { name = "GlobalStandard", capacity = 5000 }
    properties = {
      provisioningState = "Succeeded", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
      model             = { format = "Mistral AI", name = "Mistral-Large-3", version = "1" }
      capabilities      = { chatCompletion = "true" }
    }
  } }
}

run "default_render_has_no_successor_semantic_changes" {
  command = plan
  variables {
    route_manifest_path          = ""
    persistent_poc_authorized    = false
    demo_authorized              = false
    allow_product_subscriptions  = false
    glm_enabled                  = false
    glm_internal_secret_verified = false
    rpm_limit                    = 1
    tpm_limit                    = 1000
    daily_call_allowance         = 8
    completion_token_limit       = 32
  }
  assert {
    condition = (
      !local.foundry_eight_enabled && local.foundry_eight_manifest_valid &&
      local.foundry_eight_policy == local.auto_policy &&
      length(local.foundry_eight_anthropic_aliases) == 0 &&
      length(azapi_resource.foundry_eight_backend) == 0 &&
      local.route_backends == { "gpt-5.6-luna" = local.model_backend } &&
      !strcontains(local.policy, "converted[\"speed\"]") &&
      !strcontains(local.policy, "var promptTokens =") &&
      !strcontains(local.policy, "native_model_unavailable")
    )
    error_message = "The default must remain the original Luna render, with no successor code or backend activation."
  }
}

run "historical_twelve_remain_opted_out" {
  command = plan
  variables { route_manifest_path = "../../gateway/catalog/fireworks-candidate-routes.json" }
  assert {
    condition = (
      !local.foundry_eight_enabled && local.foundry_eight_manifest_valid &&
      local.foundry_eight_policy == local.glm_policy &&
      length(local.routes) == 12 && length(local.all_aliases) == 13 &&
      length(azapi_resource.foundry_eight_backend) == 0 &&
      !strcontains(local.policy, "claude-opus-5-5-fast") &&
      !strcontains(local.policy, "Mistral-Large-3")
    )
    error_message = "Selecting the historical manifest must not silently enable any of the new eight routes."
  }
}

run "explicit_manifest_is_exact_twenty_plus_external" {
  command = plan
  assert {
    condition = (
      local.foundry_eight_enabled && local.foundry_eight_manifest_valid &&
      length(local.routes) == 20 && length(local.all_aliases) == 21 &&
      toset(keys(local.routes)) == setunion(toset(keys(local.foundry_eight_original.routes)), toset(keys(local.foundry_eight_contracts))) &&
      alltrue([for alias, route in local.foundry_eight_original.routes : jsonencode(local.routes[alias]) == jsonencode(route)]) &&
      !contains(local.all_aliases, "mistral-medium-3-5") && !contains(local.all_aliases, "Decision-1") && !contains(local.all_aliases, "auto")
    )
    error_message = "Exact membership and every original route value must be preserved; no ninth deployment or Auto."
  }
  assert {
    condition = (
      length(local.foundry_eight_anthropic_aliases) == 5 &&
      local.foundry_eight_contracts["claude-opus-5-5-fast"].model_name == "claude-opus-5-5-fast" &&
      local.foundry_eight_contracts["Mistral-Large-3"].provider == "Mistral AI" &&
      local.foundry_eight_contracts["gpt-6.1-terra"].version == "2026-10-26" &&
      local.foundry_eight_contracts["gpt-6-luna"].version == "2026-09-22"
    )
    error_message = "Retained ARM model identity, case, provider and versions are not interchangeable."
  }
}

run "native_conversion_auth_speed_and_usage_contract" {
  command = plan
  assert {
    condition = (
      length(split(local.foundry_eight_native_auth, local.policy)) == 2 &&
      strcontains(local.policy, "resource=\"https://ai.azure.com\"") &&
      strcontains(local.policy, "resource=\"https://cognitiveservices.azure.com/\"") &&
      strcontains(local.policy, "Bearer {{aiflux-glm-5-3-api-key}}") &&
      length(regexall("rewrite-uri template=\"/messages\"", local.policy)) == 5 &&
      strcontains(local.policy, "role == \"system\" || role == \"developer\"") &&
      strcontains(local.policy, "[\"max_tokens\"] = (int)request[\"max_completion_tokens\"]") &&
      strcontains(local.policy, "[\"stream\"] = false") &&
      !strcontains(local.provider_rules, "claude-") &&
      strcontains(local.provider_rules, "Mistral-Large-3")
    )
    error_message = "Native conversion must run after PII with the right version/audience; Mistral remains OpenAI-compatible and existing auth is retained."
  }
  assert {
    condition = (
      length(split("<llm-content-safety", split(local.foundry_eight_native_auth, local.policy)[0])) == 3 &&
      length(regexall("<send-request mode=\"new\" response-variable-name=\"aiflux-pii\"", split(local.foundry_eight_native_auth, local.policy)[0])) == 5 &&
      strcontains(split("id=\"aiflux-anthropic-normalization\"", local.policy)[1], "<llm-content-safety") &&
      strcontains(split("window-size=\"1000\"", local.policy)[1], "aiflux-native-answer") &&
      strcontains(local.policy, "block[\"signature\"].Type == JTokenType.String") &&
      strcontains(local.policy, "Unsupported provider content") &&
      strcontains(local.policy, "[\"prompt_tokens\"] = promptTokens") &&
      strcontains(local.policy, "[\"cached_tokens\"] = cacheRead") &&
      strcontains(local.policy, "[\"cache_write_tokens\"] = cacheWrite")
    )
    error_message = "Original/redacted safety and all PII batches precede inference auth; normalized text, never thinking/signatures, must pass output safety before release."
  }
  assert {
    condition = (
      length(regexall("converted\\[\"speed\"\\] = \"fast\";", local.policy)) == 1 &&
      strcontains(local.policy, "var fast = (string)context.Variables[\"aiflux-model\"] == \"claude-opus-5-5-fast\";") &&
      strcontains(local.policy, "(string)usage[\"speed\"] != \"fast\"") &&
      strcontains(local.policy, "(string)usage[\"speed\"] != \"standard\"") &&
      strcontains(local.policy, "var inclusive = (long)input + (long)read + (long)write;") &&
      strcontains(local.policy, "long? promptTokens = cacheRead.HasValue && cacheWrite.HasValue ? knownPrompt : (long?)null;") &&
      strcontains(local.policy, "knownPrompt > int.MaxValue - (int)usage[\"output_tokens\"]") &&
      strcontains(local.policy, "Invalid provider cache usage") &&
      strcontains(local.policy, "Unsupported provider stop reason") &&
      strcontains(local.policy, "Missing provider answer")
    )
    error_message = "Fast is exact-alias-only and must be proved by usage.speed; inclusive cache totals and strict native guards are mandatory."
  }
  assert {
    condition = (
      alltrue([for header in ["api-key", "x-api-key", "apikey", "x-goog-api-key", "x-auth-token", "Proxy-Authorization", "Cookie", "anthropic-version", "anthropic-beta", "x-ms-api-key", "x-ms-authorization-auxiliary"] : strcontains(local.policy, "name=\"${header}\" exists-action=\"delete\"")]) &&
      strcontains(local.policy, "context.Response.StatusCode == 429 ? 429 : 503") &&
      strcontains(local.policy, "no fallback or retry was attempted") &&
      strcontains(local.policy, "aiflux-native-answer") &&
      length(split(local.foundry_eight_response_guard, local.policy)) == 2
    )
    error_message = "Caller provider credentials/overrides and raw native errors/headers must not escape or alter the selected route."
  }
}

run "new_and_existing_product_subscriptions_keep_same_safety_and_counters" {
  command = plan
  assert {
    condition = (
      strcontains(local.policy, "context.Subscription == null || context.Product == null || context.Product.Id != \"aiflux\"") &&
      !strcontains(local.policy, "context.Subscription.Id !=") &&
      strcontains(local.policy, "calls=\"60\" renewal-period=\"60\"") &&
      strcontains(local.policy, "tokens-per-minute=\"2048\" token-quota=\"10000\" token-quota-period=\"Daily\"") &&
      strcontains(local.policy, "calls=\"1000\" renewal-period=\"86400\"") &&
      strcontains(local.policy, "project-demo:") && strcontains(local.policy, "rpm:") && strcontains(local.policy, "tpm:") &&
      strcontains(local.policy, "modelMaximum = 1024;") &&
      !strcontains(local.policy, "first-period-start") && !strcontains(local.policy, "demo_expired") &&
      length(regexall("<llm-content-safety", local.policy)) == 3 &&
      length(regexall("<send-request mode=\"new\" response-variable-name=\"aiflux-pii\"", local.policy)) == 5 &&
      strcontains(local.policy, "pii_inspection_unavailable") &&
      !strcontains(local.policy, "<retry") && length(regexall("<forward-request", local.policy)) == 1
    )
    error_message = "Existing and future active product subscribers need no admin gate; all current safety, caps, counter identities and single-attempt semantics remain."
  }
}

run "enabled_plan_contains_only_additive_apim_backends_with_existing_children" {
  command = plan
  variables { enabled = true }
  assert {
    condition = (
      local.foundry_eight_deployments_ready &&
      toset(keys(azapi_resource.foundry_eight_backend)) == toset(["anthropic", "mistral"]) &&
      azapi_resource.foundry_eight_backend["anthropic"].parent_id == local.apim &&
      azapi_resource.foundry_eight_backend["anthropic"].body.properties.url == "https://poc-ids-token-ex-foundry.services.ai.azure.com/anthropic/v1" &&
      azapi_resource.foundry_eight_backend["mistral"].body.properties.url == "https://poc-ids-token-ex-foundry.services.ai.azure.com/openai/v1" &&
      alltrue([for backend in azapi_resource.foundry_eight_backend : backend.body.properties.tls.validateCertificateChain && backend.body.properties.tls.validateCertificateName]) &&
      length(azapi_resource.project_child) == 3 && length(azapi_resource.project_operation) == 2 &&
      length(azapi_resource.glm_named_value) == 0 && length(azapi_resource.glm_backend) == 1 &&
      length(azapi_resource.fireworks_backend) == 1 && length(azapi_resource.poc_settings) == 0
    )
    error_message = "The successor adds exactly two TLS-validated APIM backends, not models, secrets, roles, settings or alternative operations."
  }
}

run "claude_missing_actual_chat_flag_fails_closed" {
  command = plan
  variables { enabled = true }
  override_data {
    target = data.azapi_resource.route_deployment["claude-sonnet-5-5"]
    values = { output = {
      sku = { name = "GlobalStandard", capacity = 5000 }
      properties = {
        provisioningState = "Succeeded", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
        model             = { format = "Anthropic", name = "claude-sonnet-5-5", version = "2" }
        capabilities      = {}
      }
    } }
  }
  expect_failures = [azapi_resource.project_child, azapi_resource.foundry_eight_backend]
}

run "fast_cannot_bind_standard_model_identity" {
  command = plan
  variables { enabled = true }
  override_data {
    target = data.azapi_resource.route_deployment["claude-opus-5-5-fast"]
    values = { output = {
      sku = { name = "GlobalStandard", capacity = 2000 }
      properties = {
        provisioningState = "Succeeded", currentCapacity = 2000, raiPolicyName = "Microsoft.DefaultV2"
        model             = { format = "Anthropic", name = "claude-opus-5-5", version = "2" }
        capabilities      = { chatCompletion = "true" }
      }
    } }
  }
  expect_failures = [azapi_resource.project_child, azapi_resource.foundry_eight_backend]
}

run "new_route_wrong_sku_or_capacity_fails_closed" {
  command = plan
  variables { enabled = true }
  override_data {
    target = data.azapi_resource.route_deployment["Mistral-Large-3"]
    values = { output = {
      sku = { name = "DataZoneStandard", capacity = 1000 }
      properties = {
        provisioningState = "Succeeded", currentCapacity = 1000, raiPolicyName = "Microsoft.DefaultV2"
        model             = { format = "Mistral AI", name = "Mistral-Large-3", version = "1" }
        capabilities      = { chatCompletion = "true" }
      }
    } }
  }
  expect_failures = [azapi_resource.project_child, azapi_resource.foundry_eight_backend]
}

run "new_route_pending_or_wrong_version_fails_closed" {
  command = plan
  variables { enabled = true }
  override_data {
    target = data.azapi_resource.route_deployment["gpt-6.1-terra"]
    values = { output = {
      sku = { name = "GlobalStandard", capacity = 5000 }
      properties = {
        provisioningState = "Creating", currentCapacity = 5000, raiPolicyName = "Microsoft.DefaultV2"
        model             = { format = "OpenAI", name = "gpt-6.1-terra", version = "2026-09-29" }
        capabilities      = { chatCompletion = "true" }
      }
    } }
  }
  expect_failures = [azapi_resource.project_child, azapi_resource.foundry_eight_backend]
}

run "partial_manifest_is_not_an_eight_model_release" {
  command = plan
  variables { excluded_routes = ["claude-opus-4-8"] }
  assert {
    condition     = !local.foundry_eight_manifest_valid
    error_message = "No silent partial eight-model profile is allowed."
  }
}

run "preserve_detached_existing_fragment_not_runtime_flag" {
  command = plan
  variables {
    enabled                        = true
    poc_settings_bootstrap_enabled = true
    poc_controls_enabled           = false
  }
  assert {
    condition = (
      local.foundry_eight_manifest_valid &&
      length(azapi_resource.poc_settings) == 1 &&
      !strcontains(local.policy, "<include-fragment") &&
      !strcontains(local.policy, "aiflux-poc-rpm") &&
      local.foundry_eight_base_policy == local.glm_policy
    )
    error_message = "Retain the existing detached runtime-owned fragment; API runtime POC=true must not attach controls or alter quotas."
  }
}

run "attaching_controls_is_not_part_of_the_eight_model_release" {
  command = plan
  variables {
    enabled                            = true
    poc_settings_bootstrap_enabled     = true
    poc_controls_enabled               = true
    poc_publisher_permissions_verified = true
  }
  expect_failures = [azapi_resource.project_child, azapi_resource.foundry_eight_backend, azapi_resource.fireworks_backend]
}