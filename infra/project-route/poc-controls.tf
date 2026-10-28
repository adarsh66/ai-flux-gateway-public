# Isolated, default-OFF persistent POC profile. Does not enable legacy /dev/v1.
# No RBAC grant here: publisher permissions block activation, not creation.
variable "poc_settings_bootstrap_enabled" {
  type        = bool
  default     = false
  description = "Create only the detached safe-default fragment, without activating controls or claiming publisher permissions. Persist true once created."
}

variable "poc_controls_enabled" {
  type    = bool
  default = false
  validation {
    condition = !var.poc_controls_enabled || (
      var.persistent_poc_authorized && var.allow_product_subscriptions &&
      !var.candidate_validation && !var.acceptance_verified && var.poc_publisher_permissions_verified
    )
    error_message = "Scoped POC controls require persistent exact-product access and verified existing fragment publisher permissions."
  }
}

variable "poc_publisher_permissions_verified" {
  type        = bool
  default     = false
  description = "Fresh exact-identity fragment read/write metadata proof, not permission to grant roles."
}

locals {
  poc_fragment_name = "aiflux-dev-unified-poc-settings"
  # Apply replacements to the COMPLETE existing envelope, preserving original
  # locations, keys, renewal periods, all models/GLM and three safety passes.
  # calls on quota-by-key does NOT support expressions: the runtime fragment
  # compiles mutually exclusive literal caps, one existing-key quota per request.
  poc_limits_policy = replace(replace(replace(replace(local.glm_policy,
    "<quota-by-key calls=\"${var.daily_call_allowance}\" renewal-period=\"86400\" counter-key='@(\"project-demo:\" + context.Subscription.Id)' />",
    "<include-fragment fragment-id=\"${local.poc_fragment_name}\" />"),
    "<rate-limit-by-key calls=\"${var.rpm_limit}\"",
    "<rate-limit-by-key calls=\"@(context.Variables.GetValueOrDefault&lt;int&gt;(&quot;aiflux-poc-rpm&quot;, 60))\""),
    "tokens-per-minute=\"${var.tpm_limit}\"",
    "tokens-per-minute=\"@(context.Variables.GetValueOrDefault&lt;int&gt;(&quot;aiflux-poc-tpm&quot;, 2048))\""),
    "token-quota=\"${var.daily_token_quota}\"",
  "token-quota=\"@(context.Variables.GetValueOrDefault&lt;int&gt;(&quot;aiflux-poc-token-quota&quot;, 10000))\"")
  poc_hate_policy = replace(local.poc_limits_policy, "name=\"Hate\" threshold=\"${var.safety_threshold}\"",
  "name=\"Hate\" threshold=\"@(context.Variables.GetValueOrDefault&lt;int&gt;(&quot;aiflux-hate-threshold&quot;, 1))\"")
  poc_violence_policy = replace(local.poc_hate_policy, "name=\"Violence\" threshold=\"${var.safety_threshold}\"",
  "name=\"Violence\" threshold=\"@(context.Variables.GetValueOrDefault&lt;int&gt;(&quot;aiflux-violence-threshold&quot;, 1))\"")
  poc_sexual_policy = replace(local.poc_violence_policy, "name=\"Sexual\" threshold=\"${var.safety_threshold}\"",
  "name=\"Sexual\" threshold=\"@(context.Variables.GetValueOrDefault&lt;int&gt;(&quot;aiflux-sexual-threshold&quot;, 1))\"")
  poc_policy = replace(local.poc_sexual_policy, "name=\"SelfHarm\" threshold=\"${var.safety_threshold}\"",
  "name=\"SelfHarm\" threshold=\"@(context.Variables.GetValueOrDefault&lt;int&gt;(&quot;aiflux-self-harm-threshold&quot;, 1))\"")
}

resource "azapi_resource" "poc_settings" {
  count     = var.enabled && (var.poc_settings_bootstrap_enabled || var.poc_controls_enabled) ? 1 : 0
  type      = "Microsoft.ApiManagement/service/policyFragments@2024-05-01"
  parent_id = local.apim
  name      = local.poc_fragment_name
  body = { properties = {
    description = "Runtime-owned bounded POC variables and literal-call quota; stable counter identity and envelope."
    format      = "rawxml"
    value       = file("${path.module}/../../gateway/policies/poc-settings-defaults.xml")
  } }
  lifecycle {
    prevent_destroy = true
    # ONLY runtime content ownership, not ignore-all. Publisher uses ETag/hash
    # guarded readback. A later plan may not overwrite published override data.
    ignore_changes = [body.properties.value]
  }
}