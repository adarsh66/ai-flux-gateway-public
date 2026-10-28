# Isolated existing-APIM child scope. Never run a broad main-stack apply for this
# repair. The existing global policy must be imported before planning; retain a
# protected baseline and validate the exact saved plan with apim_route_repair.
terraform {
  required_version = "= 1.12.1"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "= 5.9.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "= 2.13.0"
    }
  }
}

provider "azapi" {
  subscription_id = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
}

provider "azurerm" {
  features {}
  subscription_id                 = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
  resource_provider_registrations = "none"
}

variable "enabled" {
  type        = bool
  default     = false
  description = "Candidate creation only after exact-plan validation; never inferred from defaults."
}

variable "route_manifest_path" {
  type        = string
  default     = ""
  description = "Explicit reviewed exact-project chat manifest. Empty preserves the original Luna-only route."
}

variable "excluded_routes" {
  type        = set(string)
  default     = []
  description = "Failed bounded probes may remove only their route; never removes working Luna."
  validation {
    condition     = !contains(var.excluded_routes, "gpt-5.6-luna")
    error_message = "The existing Luna route must be preserved."
  }
}

variable "safety_threshold" {
  type    = number
  default = 1
  validation {
    condition     = var.safety_threshold >= 0 && var.safety_threshold <= 7 && floor(var.safety_threshold) == var.safety_threshold
    error_message = "EightSeverityLevels accepts only integers 0 through 7. Zero also blocks benign severity-zero content."
  }
}

variable "rpm_limit" {
  type        = number
  default     = 1
  description = "Valid POST requests per subscription/model per 60 seconds. Raising defaults requires a new scoped review."
  validation {
    condition     = var.rpm_limit >= 1 && floor(var.rpm_limit) == var.rpm_limit
    error_message = "rpm_limit must be a positive integer; zero is not an unlimited-mode switch."
  }
}

variable "rate_limit_window_seconds" {
  type        = number
  default     = 60
  description = "Pinned to one minute so rpm_limit always means RPM, not calls in an arbitrary window."
  validation {
    condition     = var.rate_limit_window_seconds == 60
    error_message = "This reviewed RPM profile requires exactly 60 seconds (APIM supports at most 300)."
  }
}

variable "tpm_limit" {
  type    = number
  default = 1000
  validation {
    condition     = var.tpm_limit >= var.completion_token_limit && floor(var.tpm_limit) == var.tpm_limit
    error_message = "tpm_limit must be a positive integer at least as large as the output cap."
  }
}

variable "daily_token_quota" {
  type        = number
  default     = 10000
  description = "Prompt plus completion tokens, resetting at UTC midnight. Not a dollar budget."
  validation {
    condition     = var.daily_token_quota >= var.tpm_limit && floor(var.daily_token_quota) == var.daily_token_quota
    error_message = "daily_token_quota must be an integer at least as large as tpm_limit."
  }
}

variable "daily_call_allowance" {
  type        = number
  default     = 8
  description = "Bounded valid POSTs per existing 86400-second counter. Only a separately guarded demo update authorizes 1000; never changes counter identity or epoch."
  validation {
    condition     = contains([8, 1000], var.daily_call_allowance)
    error_message = "Only the original eight-call profile or explicitly reviewed 1000-call demo is supported."
  }
}

variable "completion_token_limit" {
  type    = number
  default = 32
  validation {
    condition     = var.completion_token_limit >= 1 && var.completion_token_limit <= 1024 && floor(var.completion_token_limit) == var.completion_token_limit
    error_message = "Output stays bounded at 32 unless the explicit persistent POC authorizes up to 1024."
  }
}

variable "backend_retries" {
  type    = number
  default = 0
  validation {
    condition     = var.backend_retries == 0
    error_message = "Backend retries are prohibited in this bounded profile."
  }
}

variable "candidate_validation" {
  type        = bool
  default     = false
  description = "Subscription-restricted validation API only; final route stays closed until actual acceptance."
}

variable "restore_global_policy" {
  type        = string
  default     = ""
  description = "Protected exact baseline for rollback only. Keeps the imported global object rather than deleting it."
}

variable "global_policy_baseline" {
  type        = string
  default     = ""
  description = "Exact protected ARM policy export; preserve existing formatting and unrelated bytes."
}

variable "global_policy_format" {
  type    = string
  default = "rawxml"
  validation {
    condition     = contains(["xml", "rawxml"], var.global_policy_format)
    error_message = "Use the exact export format, never a URL-linked policy."
  }
}

variable "acceptance_verified" {
  type        = bool
  default     = false
  description = "Actual scope-specific safety, PII, quota, identity and deployment acceptance, not default authorization or legal acceptance."
}

variable "demo_authorized" {
  type        = bool
  default     = false
  description = "Explicit temporary demo authorization only; never production acceptance."
}

variable "demo_expires_at" {
  type        = string
  default     = ""
  description = "Fixed UTC RFC3339 expiry, retained on reapply; never a sliding timestamp."
  validation {
    condition     = var.demo_expires_at == "" || can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", var.demo_expires_at))
    error_message = "Demo expiry must be a fixed UTC timestamp."
  }
}

variable "persistent_poc_authorized" {
  type        = bool
  default     = false
  description = "Explicit no-deadline POC only, not production acceptance; retains all authentication, quotas and safety."
  validation {
    condition = var.persistent_poc_authorized ? (
      var.demo_authorized && !var.acceptance_verified && !var.candidate_validation && var.demo_expires_at == "" &&
      var.rpm_limit == 60 && var.tpm_limit == 2048 && var.daily_token_quota == 10000 &&
      var.daily_call_allowance == 1000 && var.completion_token_limit == 1024 &&
      var.backend_retries == 0 && var.safety_threshold == 1
    ) : var.completion_token_limit <= 32
    error_message = "Persistent POC requires exactly output1024/TPM2048/RPM60/daily10000/calls1000, empty expiry, retry0, threshold1 and no acceptance."
  }
}

variable "allow_product_subscriptions" {
  type        = bool
  default     = false
  description = "Explicit persistent-POC opt-in for active aiflux product subscriptions; never anonymous, candidate or production access."
  validation {
    condition     = !var.allow_product_subscriptions || (var.persistent_poc_authorized && !var.candidate_validation && !var.acceptance_verified)
    error_message = "Product subscription access requires the explicit persistent POC, not candidate validation or production acceptance."
  }
}

locals {
  rg                = "/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC"
  apim              = "${local.rg}/providers/Microsoft.ApiManagement/service/poc-ids-token-ex-apim"
  account           = "${local.rg}/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
  project           = "${local.account}/projects/poc-ids-token-ex-foundry-project"
  project_endpoint  = "https://poc-ids-token-ex-foundry.services.ai.azure.com/api/projects/poc-ids-token-ex-foundry-project"
  subscriber        = "e9f2abb0-930b-598a-b210-0ab0b279127f"
  gateway_client    = "5792b72e-1605-4dce-a594-4c430a5af619"
  model             = "gpt-5.6-luna"
  model_version     = "2026-07-09"
  route_manifest    = var.route_manifest_path == "" ? null : jsondecode(file(var.route_manifest_path))
  routes            = var.route_manifest_path == "" ? { (local.model) = { version = local.model_version, provider = "OpenAI", token_parameter = "max_completion_tokens" } } : { for alias, route in local.route_manifest.routes : alias => route if !contains(var.excluded_routes, alias) }
  model_backend     = "aiflux-project-gpt-5-6-luna"
  fireworks_backend = "aiflux-project-fireworks"
  fireworks_url     = "https://poc-ids-token-ex-foundry.services.ai.azure.com/openai/v1"
  fireworks_contracts = {
    "FW-GLM-5.3"    = { version = "2", sku = "GlobalStandard" }
    "FW-MiniMax-M3" = { version = "1", sku = "DataZoneStandard" }
  }
  fireworks_aliases   = sort(setintersection(toset(keys(local.routes)), toset(keys(local.fireworks_contracts))))
  route_backends      = { for alias in keys(local.routes) : alias => contains(local.fireworks_aliases, alias) ? local.fireworks_backend : local.model_backend }
  safety_backend      = "aiflux-project-safety"
  origins             = ["https://poc-ids-token-ex-customer.azurewebsites.net", "https://poc-ids-token-ex-admin.azurewebsites.net"]
  model_list          = jsonencode({ object = "list", data = [for alias in local.all_aliases : { id = alias, object = "model", owned_by = "aiflux" }] })
  subscription_clause = "context.Product.Id != \"aiflux\""
  api_name            = var.candidate_validation ? "aiflux-project-validation" : "aiflux-dev-unified"
  api_path            = var.candidate_validation ? "dev/llm/validate/v1" : "dev/llm/v1"

  # Reuse the original/redacted/output safety and batched fail-closed PII
  # contracts without changing the legacy multi-region/Anthropic profile.
  shared_policy = templatefile("${path.module}/../../gateway/policies/dev-openai.xml.tftpl", {
    language_endpoint            = "https://poc-ids-token-ex-foundry.cognitiveservices.azure.com"
    gateway_identity_client      = local.gateway_client
    tpm_limit                    = var.tpm_limit
    rpm_limit                    = var.rpm_limit
    completion_token_limit       = var.completion_token_limit
    safety_threshold             = tostring(var.safety_threshold)
    admin_settings_enabled       = false
    settings_fragment_id         = ""
    safety_backend_id            = local.safety_backend
    unified                      = true
    product_id                   = "aiflux"
    cors_origins                 = local.origins
    model_list                   = local.model_list
    model_alias_conditions       = join(" || ", [for alias in local.all_aliases : "(string)model == \"${alias}\""])
    model_completion_limits      = jsonencode({ for alias in keys(local.routes) : alias => var.completion_token_limit })
    anthropic_alias_conditions   = "false"
    model_limit_rules            = join(" ", [for alias in local.all_aliases : "if ((string)model == \"${alias}\") { modelMaximum = ${var.completion_token_limit}; }"])
    openai_aliases               = sort(keys(local.routes))
    openai_pool_ids              = local.route_backends
    foundry_aliases              = []
    foundry_api_versions         = {}
    anthropic_aliases            = []
    anthropic_context_conditions = "false"
    anthropic_backend_ids        = {}
  })
  # This API is created with explicit operations, not an imported OpenAPI schema.
  # validate-content's implicit schema is therefore absent. Keep the same byte
  # cap and strict object parsing here; the shared shape/model checks still run.
  request_validation = <<-XML
    <choose><when condition='@{
      try {
        var raw = context.Request.Body.As&lt;string&gt;(preserveContent: true);
        if (raw == null || System.Text.Encoding.UTF8.GetByteCount(raw) > 16384) { return true; }
        JObject.Parse(raw);
        return false;
      } catch { return true; }
    }'><return-response><set-status code="400" reason="Invalid request" /><set-header name="Content-Type" exists-action="override"><value>application/json</value></set-header><set-body>{"error":{"code":"invalid_request_body","message":"A bounded JSON object is required."}}</set-body></return-response></when></choose>
  XML
  # Public contract stays max_completion_tokens. Provider normalization occurs
  # only after input validation, safety and PII, on an exact allowlisted route.
  provider_rules    = join(" ", [for alias, route in local.routes : route.token_parameter == "max_tokens" ? "if ((string)request[\"model\"] == \"${alias}\") { request[\"max_tokens\"] = request[\"max_completion_tokens\"]; request.Remove(\"max_completion_tokens\"); }" : ""])
  provider_policy   = replace(replace(local.shared_policy, "\r\n", "\n"), "return request.ToString();\n        }]]></set-body>", "${local.provider_rules} return request.ToString();\n        }]]></set-body>")
  validated_policy  = replace(local.provider_policy, "/(?s)<validate-content id=\"aiflux-request-validation\".*?</validate-content>/", local.request_validation)
  subscriber_policy = var.allow_product_subscriptions ? local.validated_policy : replace(local.validated_policy, local.subscription_clause, "${local.subscription_clause} || context.Subscription.Id != \"${local.subscriber}\"")
  # Match rendered attributes, not a hardcoded numeric substring. Keep
  # existing counter keys stable across reapply/candidate/final and limit edits:
  # no timestamp, release ID, policy hash, API name or limit value in a key.
  rate_policy = replace(local.subscriber_policy, "calls=\"${var.rpm_limit}\" renewal-period=\"60\"", "calls=\"${var.rpm_limit}\" renewal-period=\"${var.rate_limit_window_seconds}\" remaining-calls-header-name=\"x-aiflux-rpm-remaining\" total-calls-header-name=\"x-aiflux-rpm-limit\"")
  token_policy = replace(local.rate_policy,
    "tokens-per-minute=\"${var.tpm_limit}\" estimate-prompt-tokens=\"true\"",
  "tokens-per-minute=\"${var.tpm_limit}\" token-quota=\"${var.daily_token_quota}\" token-quota-period=\"Daily\" estimate-prompt-tokens=\"true\" remaining-tokens-header-name=\"x-aiflux-tpm-remaining\" remaining-quota-tokens-header-name=\"x-aiflux-daily-tokens-remaining\"")
  # A validation API stays at eight calls. The existing final demo can receive
  # a separately authorized bounded increase without changing its counter key.
  demo_expiry_policy = var.demo_authorized && !var.persistent_poc_authorized ? "<choose><when condition='@(DateTime.UtcNow >= DateTime.Parse(\"${var.demo_expires_at}\"))'><return-response><set-status code=\"403\" reason=\"Demo expired\" /><set-header name=\"Content-Type\" exists-action=\"override\"><value>application/json</value></set-header><set-body>{\"error\":{\"code\":\"demo_expired\",\"message\":\"The authorized demo window has ended.\"}}</set-body></return-response></when></choose>" : ""
  demo_policy        = var.demo_authorized ? replace(replace(local.token_policy, "\r\n", "\n"), "<base />\n    <choose>\n      <when condition='@(context.Subscription", "<base />${local.demo_expiry_policy}\n    <choose>\n      <when condition='@(context.Subscription") : local.token_policy
  quota_policy       = var.candidate_validation || var.demo_authorized ? replace(local.demo_policy, "<rate-limit-by-key", "<quota-by-key calls=\"${var.demo_authorized ? var.daily_call_allowance : 8}\" renewal-period=\"86400\" counter-key='@(\"${var.demo_authorized ? "project-demo" : "project-validation"}:\" + context.Subscription.Id)' /><rate-limit-by-key") : local.demo_policy
  # No <retry count="0">: APIM requires count >= 1. Remove the entire retry
  # wrapper and its rebinding logic, not just its count. One forward only.
  # Outbound usage reads this int on successful POSTs. Initialize it after
  # inbound checks, before forwarding; backend permits exactly one policy.
  attempt_policy = replace(var.poc_controls_enabled ? local.poc_policy : local.glm_policy, "</inbound>", "<set-variable name=\"aiflux-backend-attempt\" value=\"@(1)\" /></inbound>")
  forward_policy = replace(local.attempt_policy, "/(?s)<backend>.*?</backend>/", "<backend><forward-request timeout=\"45\" buffer-request-body=\"true\" buffer-response=\"true\" fail-on-error-status-code=\"false\" /></backend>")
  # Bounded candidate/demo diagnostics expose a fixed stage only, never
  # LastError.Message, request/response text, tokens or backend traces.
  error_cors        = <<-XML
      <set-header name="Access-Control-Allow-Origin" exists-action="override"><value>@((context.Request.Headers.GetValueOrDefault("Origin", "") == "${local.origins[0]}" || context.Request.Headers.GetValueOrDefault("Origin", "") == "${local.origins[1]}") ? context.Request.Headers.GetValueOrDefault("Origin", "") : "")</value></set-header>
      <set-header name="Vary" exists-action="append"><value>Origin</value></set-header>
      <set-header name="Access-Control-Expose-Headers" exists-action="override"><value>Retry-After, x-aiflux-failure-stage</value></set-header>
  XML
  call_quota_error  = <<-XML
    <choose><when condition='@(context.LastError.Source == "quota-by-key" &amp;&amp; context.LastError.Reason == "QuotaExceeded")'><return-response>
      <set-status code="403" reason="Bounded demo call quota exceeded" />
      <set-header name="Content-Type" exists-action="override"><value>application/json</value></set-header>
      <set-header name="Retry-After" exists-action="override"><value>86400</value></set-header>
      <set-body>{"error":{"code":"bounded_call_quota_exceeded","message":"The bounded daily call allowance is exhausted."}}</set-body>
    </return-response></when></choose>
  XML
  error_diagnostics = var.candidate_validation || var.demo_authorized ? "<set-header name=\"x-aiflux-failure-stage\" exists-action=\"override\"><value>@(context.LastError.Source == \"llm-content-safety\" ? \"safety\" : context.LastError.Source == \"send-request\" ? \"pii\" : context.LastError.Source == \"authentication-managed-identity\" ? \"identity\" : context.LastError.Source == \"llm-token-limit\" ? \"tokens\" : context.LastError.Source == \"rate-limit-by-key\" ? \"rpm\" : context.LastError.Source == \"quota-by-key\" ? \"quota\" : \"other\")</value></set-header>" : ""
  # return-response creates its response: headers must be set inside each
  # return-response, not on the discarded pre-error response object.
  error_policy = "${local.call_quota_error}${split("<on-error>", local.forward_policy)[1]}"
  policy       = "${split("<on-error>", local.forward_policy)[0]}<on-error>${replace(local.error_policy, "/(<set-status[^>]*\\/>)/", "$1${local.error_cors}${local.error_diagnostics}")}"
  default_global_template = templatefile("${path.module}/../../gateway/policies/global-dev-gate.xml.tftpl", {
    enabled         = false
    unified_enabled = true
  })
  global_template = var.global_policy_baseline != "" ? replace(var.global_policy_baseline, "|| ((false)", "|| ((true)") : local.default_global_template
  # Candidate opens ONLY the separate validation path. Legacy and final paths
  # remain closed; the same full subscriber/safety/PII/token policy is mandatory.
  global_policy = var.candidate_validation ? replace(local.global_template, "dev/llm/v1/", "dev/llm/validate/v1/") : local.global_template
  children = {
    backend = {
      type      = "Microsoft.ApiManagement/service/backends@2024-05-01"
      parent_id = local.apim
      name      = local.model_backend
      body = { properties = {
        protocol = "http", url = "https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1"
        tls      = { validateCertificateChain = true, validateCertificateName = true }
      } }
    }
    safety = {
      type      = "Microsoft.ApiManagement/service/backends@2024-06-01-preview"
      parent_id = local.apim
      name      = local.safety_backend
      body = { properties = {
        protocol    = "http", url = "https://poc-ids-token-ex-safety.cognitiveservices.azure.com"
        tls         = { validateCertificateChain = true, validateCertificateName = true }
        credentials = { managedIdentity = { resource = "https://cognitiveservices.azure.com", clientId = local.gateway_client } }
      } }
    }
    api = {
      type      = "Microsoft.ApiManagement/service/apis@2024-05-01"
      parent_id = local.apim
      name      = local.api_name
      body = { properties = {
        displayName                   = "AIFLUX exact-project bounded chat", path = local.api_path
        protocols                     = ["https"], subscriptionRequired = true
        subscriptionKeyParameterNames = { header = "Ocp-Apim-Subscription-Key", query = "subscription-key" }
      } }
    }
  }
}

data "azapi_resource" "deployment" {
  count                  = var.enabled ? 1 : 0
  type                   = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  parent_id              = local.account
  name                   = local.model
  response_export_values = ["properties", "sku"]
}

data "azapi_resource" "project" {
  count                  = var.enabled ? 1 : 0
  type                   = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  parent_id              = local.account
  name                   = "poc-ids-token-ex-foundry-project"
  response_export_values = ["properties"]
}

data "azapi_resource" "route_deployment" {
  for_each               = var.enabled && var.route_manifest_path != "" ? local.routes : {}
  type                   = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  parent_id              = local.account
  name                   = each.key
  response_export_values = ["properties", "sku"]
}

resource "azapi_resource" "project_child" {
  for_each                  = { for key, value in local.children : key => value if var.enabled }
  type                      = each.value.type
  parent_id                 = each.value.parent_id
  name                      = each.value.name
  body                      = each.value.body
  schema_validation_enabled = false
  lifecycle {
    precondition {
      condition = var.route_manifest_path == "" || (
        local.route_manifest.project_endpoint == local.project_endpoint &&
        local.route_manifest.upstream_url == "https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1" &&
        contains(keys(local.routes), local.model) &&
        alltrue([for alias, route in local.routes : can(regex("^[A-Za-z0-9][A-Za-z0-9.-]*$", alias)) && contains(["max_tokens", "max_completion_tokens"], route.token_parameter)]) &&
        alltrue([for alias, deployment in data.azapi_resource.route_deployment :
          deployment.output.properties.provisioningState == "Succeeded" &&
          deployment.output.properties.model.name == try(local.routes[alias].model_name, alias) &&
          deployment.output.properties.model.version == local.routes[alias].version &&
          deployment.output.properties.model.format == local.routes[alias].provider &&
          (contains(local.fireworks_aliases, alias) ? (
            local.routes[alias].provider == "Fireworks" &&
            local.routes[alias].version == local.fireworks_contracts[alias].version &&
            try(local.routes[alias].upstream_url, "") == local.fireworks_url &&
            deployment.output.sku.name == local.fireworks_contracts[alias].sku
          ) : try(local.routes[alias].upstream_url, local.route_manifest.upstream_url) == local.route_manifest.upstream_url) &&
          deployment.output.properties.currentCapacity > 0 &&
          deployment.output.properties.capabilities.chatCompletion == "true" &&
          contains(["Active", "Succeeded"], coalesce(try(deployment.output.properties.deploymentState, null), "Active"))
        ])
      )
      error_message = "Multi-model routes require fresh exact-project deployment identities, active chat capacity and reviewed provider dialects."
    }
    precondition {
      condition = (
        !strcontains(local.policy, "<retry") &&
        length(regexall("<forward-request", local.policy)) == 1 &&
        (var.allow_product_subscriptions ? (
          strcontains(local.policy, "context.Subscription == null || context.Product == null || context.Product.Id != \"aiflux\"") &&
          !strcontains(local.policy, "context.Subscription.Id != \"${local.subscriber}\"")
        ) : strcontains(local.policy, "context.Subscription.Id != \"${local.subscriber}\"")) &&
        (var.poc_controls_enabled ? strcontains(local.policy, "aiflux-poc-token-quota") && strcontains(local.policy, "token-quota-period=\"Daily\"") : strcontains(local.policy, "token-quota=\"${var.daily_token_quota}\" token-quota-period=\"Daily\"")) &&
        length(regexall("<rate-limit-by-key", local.policy)) == 1 &&
        length(regexall("<llm-token-limit", local.policy)) == 1 &&
        (var.poc_controls_enabled ? strcontains(local.policy, "aiflux-poc-rpm") && strcontains(local.policy, "renewal-period=\"60\"") : strcontains(local.policy, "calls=\"${var.rpm_limit}\" renewal-period=\"${var.rate_limit_window_seconds}\"")) &&
        length(regexall("<llm-content-safety", local.policy)) == 3 &&
        strcontains(local.policy, "pii_inspection_unavailable")
      )
      error_message = "Shared policy contract changed: subscriber, token quota, no-retry and mandatory safety/PII must be re-reviewed."
    }
    precondition {
      condition     = (var.candidate_validation || var.acceptance_verified || var.demo_authorized) && var.safety_threshold == 1
      error_message = "Activation requires real acceptance or an explicit bounded candidate/demo authorization."
    }
    precondition {
      condition = !var.demo_authorized || var.persistent_poc_authorized || (
        !var.candidate_validation && !var.acceptance_verified &&
        try(timecmp(var.demo_expires_at, plantimestamp()) > 0 && timecmp(var.demo_expires_at, timeadd(plantimestamp(), "24h")) <= 0, false) &&
        var.rpm_limit == 60 && var.tpm_limit == 1000 && var.daily_token_quota == 10000 &&
        strcontains(local.policy, "demo_expired") && strcontains(local.policy, "project-demo:")
      )
      error_message = "Demo must be separate from acceptance/candidate, expire within 24h, and preserve the authorized low limits and stable quota."
    }
    precondition {
      condition = (
        data.azapi_resource.deployment[0].output.properties.provisioningState == "Succeeded" &&
        data.azapi_resource.deployment[0].output.properties.model.format == "OpenAI" &&
        data.azapi_resource.deployment[0].output.properties.model.name == local.model &&
        data.azapi_resource.deployment[0].output.properties.model.version == local.model_version &&
        data.azapi_resource.deployment[0].output.properties.currentCapacity > 0 &&
        data.azapi_resource.deployment[0].output.properties.capabilities.chatCompletion == "true" &&
        try(data.azapi_resource.deployment[0].output.properties.deploymentState, null) != "Disabled" &&
        data.azapi_resource.project[0].output.properties.provisioningState == "Succeeded" &&
        data.azapi_resource.project[0].output.properties.endpoints["AI Foundry API"] == local.project_endpoint
      )
      error_message = "Fresh exact-project ARM deployment/version/endpoint checks failed; never substitute another account or model."
    }
  }
}

resource "azapi_resource" "project_operation" {
  for_each  = var.enabled ? { models = { method = "GET", path = "/models" }, chat = { method = "POST", path = "/chat/completions" } } : {}
  type      = "Microsoft.ApiManagement/service/apis/operations@2024-05-01"
  parent_id = "${local.apim}/apis/${local.api_name}"
  name      = each.key
  body = { properties = {
    displayName = each.key, method = each.value.method, urlTemplate = each.value.path
  } }
  depends_on = [azapi_resource.project_child]
}

resource "azurerm_api_management_product_api" "project_binding" {
  count               = var.enabled ? 1 : 0
  resource_group_name = "IDS-TOKEN-EXCHANGE-POC"
  api_management_name = "poc-ids-token-ex-apim"
  product_id          = "aiflux"
  api_name            = local.api_name
  depends_on          = [azapi_resource.project_child]
}

resource "azapi_resource" "project_policy" {
  count      = var.enabled ? 1 : 0
  type       = "Microsoft.ApiManagement/service/apis/policies@2024-05-01"
  parent_id  = "${local.apim}/apis/${local.api_name}"
  name       = "policy"
  body       = { properties = { format = "rawxml", value = local.policy } }
  depends_on = [azapi_resource.project_operation, azurerm_api_management_product_api.project_binding, azapi_resource.glm_named_value, azapi_resource.glm_backend, azapi_resource.poc_settings, azapi_resource.fireworks_backend]
}

# Existing object: import, do not create over an unreviewed existing baseline.
resource "azapi_resource" "project_global_gate" {
  count      = var.enabled || var.restore_global_policy != "" ? 1 : 0
  type       = "Microsoft.ApiManagement/service/policies@2024-05-01"
  parent_id  = local.apim
  name       = "policy"
  body       = { properties = { format = var.global_policy_format, value = var.restore_global_policy != "" ? var.restore_global_policy : local.global_policy } }
  depends_on = [azapi_resource.project_policy]
}

output "candidate_policy" {
  value = local.policy
}

output "correct_project" {
  value = { resource_id = local.project, endpoint = local.project_endpoint, deployment = local.model, version = local.model_version }
}
