# SOURCE ONLY. No resources, roles, identities, keys or runtime settings.
variable "auto_routing_enabled" {
  type        = bool
  default     = false
  description = "Platform release switch, never a tenant approval. Actual APIM-native MI/response proof and independent release review are required."
  validation {
    condition = !var.auto_routing_enabled || (
      var.persistent_poc_authorized && var.demo_authorized && var.allow_product_subscriptions &&
      !var.candidate_validation && !var.acceptance_verified &&
      !var.admin_settings_enabled && !var.poc_controls_enabled &&
      local.auto_release_validation_satisfied &&
      local.auto_inputs_bound &&
      local.auto_routes_bound &&
      length(regexall("<(?:rate-limit-by-key|llm-token-limit) [^>]+/>", local.glm_policy)) == 2 &&
      length(local.auto_safety_parts) == 3 &&
      length(split(local.auto_selection_anchor, local.glm_policy)) == 2
    )
    error_message = "Auto requires actual reviewed runtime evidence OR an explicit source-bound bounded direct-release contract, source-bound defaults, existing product authorization, all candidates and detached POC fragments."
  }
}

variable "auto_routing_direct_release" {
  description = "Explicit production acceptance of pending runtime validation, NOT runtime evidence. Parent owns independent review, two-attempt ledger, fresh protected reads and rollback. Null preserves diagnostic-proof-only activation."
  type = object({
    mode                        = string
    defaults_sha256             = string
    predecessor_sha256          = string
    candidate_sha256            = string
    independent_review_sha256   = string
    rollback_sha256             = string
    max_auto_attempts           = number
    max_scoring_calls           = number
    max_completion_calls        = number
    retries                     = number
    fallback                    = bool
    runtime_validation_pending  = bool
    stop_on_explicit_regression = bool
  })
  default = null
  validation {
    condition = var.auto_routing_direct_release == null ? true : try(
      var.auto_routing_direct_release.mode == "bounded-production-direct-v1" &&
      var.auto_routing_direct_release.max_auto_attempts == 2 &&
      var.auto_routing_direct_release.max_scoring_calls == 2 &&
      var.auto_routing_direct_release.max_completion_calls == 2 &&
      var.auto_routing_direct_release.retries == 0 && !var.auto_routing_direct_release.fallback &&
      var.auto_routing_direct_release.runtime_validation_pending &&
      var.auto_routing_direct_release.stop_on_explicit_regression &&
      alltrue([for hash in [var.auto_routing_direct_release.defaults_sha256,
        var.auto_routing_direct_release.predecessor_sha256, var.auto_routing_direct_release.candidate_sha256,
        var.auto_routing_direct_release.independent_review_sha256, var.auto_routing_direct_release.rollback_sha256
    ] : can(regex("^[0-9a-f]{64}$", hash))]), false)
    error_message = "Direct release must bind exact sources, actual independent review and rollback, acknowledge pending runtime validation and cap acceptance at two attempts with no retries/fallback. Hashes alone are not review or runtime proof."
  }
}

variable "auto_routing_runtime_evidence_sha256" {
  type        = string
  default     = ""
  description = "Hash of independently reviewed actual gateway-MI scoring/response verification. Empty blocks activation; fixtures and role metadata are not this proof."
  validation {
    condition     = var.auto_routing_runtime_evidence_sha256 == "" || can(regex("^[0-9a-f]{64}$", var.auto_routing_runtime_evidence_sha256))
    error_message = "Evidence must be an exact SHA256, not an endpoint or token."
  }
}

variable "admin_settings_enabled" {
  type        = bool
  default     = false
  description = "Compatibility guard only; this isolated module never activates the legacy admin settings fragment. Auto forbids it."
}

locals {
  # Hashes bind the Auto composition boundary BEFORE native-provider wrapping.
  # The independent saved-plan review must ALSO bind the final local.policy.
  # This is an acceptance contract, not an automatic paid-call budget enforcer.
  auto_direct_release_valid = var.auto_routing_direct_release == null ? false : try(
    local.successor22_enabled && var.auto_routing_runtime_evidence_sha256 == "" &&
    var.auto_routing_direct_release.defaults_sha256 == local.auto_version &&
    var.auto_routing_direct_release.predecessor_sha256 == sha256(local.glm_policy) &&
  var.auto_routing_direct_release.candidate_sha256 == sha256(local.auto_with_error), false)
  auto_release_validation_satisfied = can(regex("^[0-9a-f]{64}$", var.auto_routing_runtime_evidence_sha256)) || local.auto_direct_release_valid
  auto_defaults_path                = "${path.module}/../../services/control-plane/src/aiflux/pricing/auto-routing-defaults.json"
  auto_prices_path                  = "${path.module}/../../services/control-plane/src/aiflux/pricing/rates-20261027.json"
  auto_catalog_path                 = "${path.module}/../../gateway/catalog/foundry-inventory-20261026.json"
  auto_defaults                     = jsondecode(file(local.auto_defaults_path))
  auto_prices                       = jsondecode(file(local.auto_prices_path))
  auto_catalog                      = jsondecode(file(local.auto_catalog_path))
  auto_version                      = filesha256(local.auto_defaults_path)
  auto_inputs_bound                 = local.auto_defaults.schema == 1 && local.auto_defaults.catalog_sha256 == filesha256(local.auto_catalog_path) && local.auto_defaults.pricing_sha256 == filesha256(local.auto_prices_path)
  auto_candidates                   = local.auto_defaults.candidates
  auto_routes_bound = alltrue([for alias in local.auto_candidates : try(
    local.routes[alias].version == local.auto_descriptors[alias].model_version &&
    local.routes[alias].provider == local.auto_descriptors[alias].provider &&
    local.routes[alias].token_parameter == one([for r in local.auto_catalog.routes : r.upstream_token_parameter if r.alias == alias]) &&
  local.route_manifest.upstream_url == "https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1", false)])
  auto_descriptors = { for alias in local.auto_candidates : alias => {
    id                    = alias
    provider              = one([for d in local.auto_catalog.deployments : d.model_format if d.name == alias])
    model_name            = one([for d in local.auto_catalog.deployments : d.model_name if d.name == alias])
    model_version         = one([for d in local.auto_catalog.deployments : d.model_version if d.name == alias])
    capabilities          = ["chat"]
    max_completion_tokens = var.completion_limits_path == "" ? min(1024, one([for r in local.auto_catalog.routes : r.max_completion_tokens if r.alias == alias])) : local.effective_completion_limits[alias]
    context_window        = null
    capability_source     = "accepted-foundry-route-inventory"
    capability_checked_at = local.auto_catalog.verified_at
    operator_preference   = "general text option; no benchmark quality ranking"
    descriptor_version    = local.auto_defaults.descriptor_version
    price_status          = one([for r in local.auto_prices.rates : r.status == "unknown" ? "unknown" : (r.status == "public_list" ? "published" : "provisional") if r.model == alias])
    price = one([for r in local.auto_prices.rates : r.status == "unknown" ? null : merge(r, {
      revision = local.auto_prices.revision, manifest_sha256 = filesha256(local.auto_prices_path), currency = "USD",
      unit     = local.auto_prices.unit, checked_at = local.auto_prices.checked_at, source_url = local.auto_prices.sources[r.source],
      basis    = local.auto_prices.basis, assumptions = local.auto_prices.assumptions, applicable_from = local.auto_prices.applicable_from
    }) if r.model == alias])
  } }
  auto_profiles = { for profile, rubric in local.auto_defaults.profiles : profile => {
    candidate_models = [for alias in local.auto_candidates : alias if profile != "cost" || local.auto_descriptors[alias].price != null]
    fallback_model   = local.auto_defaults.fallback_model
    instructions     = "${rubric}${local.auto_defaults.instructions_suffix}"
  } }
  auto_arguments = {
    snapshot_base64 = base64encode(jsonencode({ version = local.auto_completion_version, profiles = local.auto_profiles, candidates = local.auto_descriptors }))
    # Runtime-owned fragment supplies prices only. Bootstrap/publisher must
    # install the mode envelope before the one-time policy inclusion release.
    # Never copy its value into the API policy or reset it during later releases.
    pricing_fragment     = local.poc_fragment_name
    gateway_client       = local.gateway_client
    completion_limit     = var.completion_token_limit
    candidate_conditions = join(" || ", [for alias in local.auto_candidates : "(string)model == \"${alias}\""])
    manifest_conditions  = join(" || ", [for alias in keys(local.routes) : "(string)model == \"${alias}\""])
    selected_limit_rules = join(" ", [for alias in keys(local.routes) : "if ((string)model == \"${alias}\") { modelMaximum = ${local.effective_completion_limits[alias]}; }"])
    selected_limits      = local.auto_model_limits
    provider_rules       = local.provider_rules
  }
  # Move, do not duplicate, the original selected-model limits. Keep their
  # exact keys/quotas/periods. The shared daily CALL quota remains at admission,
  # once, and precedes both scoring and inference, even on resolver failures.
  auto_model_limits = join("\n        ", regexall("<(?:rate-limit-by-key|llm-token-limit) [^>]+/>", local.glm_policy))
  auto_admission    = <<-XML
    <set-variable name="aiflux-auto" value='@((string)context.Variables["aiflux-model"] == "auto")' />
    <choose><when condition='@((bool)context.Variables["aiflux-auto"])'>
      <rate-limit-by-key calls="6" renewal-period="60" counter-key='@("auto-admission:" + context.Subscription.Id)' />
    </when><otherwise>${local.auto_model_limits}</otherwise></choose>
  XML
  auto_shape = replace(replace(replace(local.glm_policy,
    "p.Name == \"model\" || p.Name == \"messages\"",
    "p.Name == \"model\" || (p.Name == \"routing_profile\" &amp;&amp; body[\"model\"] != null &amp;&amp; body[\"model\"].Type == JTokenType.String &amp;&amp; (string)body[\"model\"] == \"auto\") || p.Name == \"messages\""),
    "var modelMaximum = 0;",
    "var modelMaximum = 0; if (model != null &amp;&amp; model.Type == JTokenType.String &amp;&amp; (string)model == \"auto\") { modelMaximum = ${var.completion_token_limit}; } if (body[\"routing_profile\"] != null &amp;&amp; (body[\"routing_profile\"].Type != JTokenType.String || !new [] { \"balanced\", \"cost\", \"quality\" }.Contains((string)body[\"routing_profile\"]))) { return true; }"),
    "return model == null || model.Type != JTokenType.String || !(",
  "return model == null || model.Type != JTokenType.String || !((string)model == \"auto\" || ")
  # Replace only the original rate+token nodes, AFTER daily quota composition.
  auto_without_model_limits = replace(local.auto_shape, "/<(?:rate-limit-by-key|llm-token-limit) [^>]+\\/>/", "")
  # The quota sits immediately after aiflux-model. Insert admission AFTER it,
  # before the first safety pass. No scoring receives original unredacted text.
  auto_safety_anchor = "        <llm-content-safety backend-id=\"${local.safety_backend}\" shield-prompt=\"true\">"
  auto_safety_parts  = split(local.auto_safety_anchor, local.auto_without_model_limits)
  auto_single_admission = join(local.auto_safety_anchor, concat(
    ["${local.auto_safety_parts[0]}${local.auto_admission}"], slice(local.auto_safety_parts, 1, length(local.auto_safety_parts))
  ))
  # Rendered backend-selection anchor, not template directives.
  auto_selection_anchor = "        <choose>\n          <when condition='@((string)context.Variables[\"aiflux-model\"] == \"${sort(keys(local.routes))[0]}\")'>"
  auto_with_resolver = replace(local.auto_single_admission, local.auto_selection_anchor,
  "${templatefile("${path.module}/../../gateway/policies/auto-resolve.xml.tftpl", local.auto_arguments)}${local.auto_selection_anchor}")
  # GLM inserts its final response immediately before the closing tag, removing
  # the original indentation anchor. Match the unique tag, not its whitespace.
  auto_with_metadata = replace(local.auto_with_resolver, "</outbound>",
  "${file("${path.module}/../../gateway/policies/auto-metadata.xml")}</outbound>")
  auto_with_error = replace(local.auto_with_metadata, "  <on-error>",
  "  <on-error>${file("${path.module}/../../gateway/policies/auto-error.xml")}")
  # Exact identity when off: NO empty interpolation, whitespace or template edits.
  auto_policy = var.auto_routing_enabled ? local.auto_with_error : local.glm_policy
}
