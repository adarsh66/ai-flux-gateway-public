# Phase one reservation in the existing API/state owner. Actual 2026-10-29
# readback showed revision-copy PUT ignored isOnline=false. Request flags are
# NOT an offline guarantee; a separately reviewed PATCH and readback are needed.
# This is not Auto activation or permission to invoke the revision.
variable "auto_staging_revision" {
  type = object({
    revision        = string
    owner_nonce     = string
    baseline_sha256 = string
  })
  default     = null
  nullable    = true
  description = "Source-bound offline staging reservation. Online policy/probe/promotion require separate exact plans and actual independent review."
  validation {
    condition = var.auto_staging_revision == null ? true : (
      can(regex("^[2-9][0-9]{0,5}$|^1[0-9]{1,5}$", var.auto_staging_revision.revision)) &&
      can(regex("^[0-9a-f]{32}$", var.auto_staging_revision.owner_nonce)) &&
      can(regex("^[0-9a-f]{64}$", var.auto_staging_revision.baseline_sha256))
    )
    error_message = "An exact noncurrent numeric revision, unique ownership nonce and fresh complete baseline SHA256 are required."
  }
}

resource "azapi_resource" "auto_stage_revision" {
  count                     = var.auto_staging_revision == null ? 0 : 1
  type                      = "Microsoft.ApiManagement/service/apis@2024-05-01"
  parent_id                 = local.apim
  name                      = "aiflux-dev-unified;rev=${var.auto_staging_revision.revision}"
  schema_validation_enabled = false
  body = { properties = {
    path                   = "dev/llm/v1"
    sourceApiId            = "${local.apim}/apis/aiflux-dev-unified"
    apiRevision            = var.auto_staging_revision.revision
    apiRevisionDescription = "Auto offline stage owner=${var.auto_staging_revision.owner_nonce} baseline=${var.auto_staging_revision.baseline_sha256}"
    isCurrent              = false
    isOnline               = false
  } }
  response_export_values = ["id", "properties"]
  lifecycle {
    prevent_destroy = true
    precondition {
      condition = (
        var.enabled && var.demo_authorized && var.persistent_poc_authorized &&
        var.allow_product_subscriptions && !var.candidate_validation &&
        !var.acceptance_verified && !var.auto_routing_enabled &&
        !var.poc_controls_enabled && !var.admin_settings_enabled &&
        local.api_name == "aiflux-dev-unified" && local.api_path == "dev/llm/v1"
      )
      error_message = "Offline staging only on the existing product-scoped development API; all activation switches must remain off."
    }
  }
}

# Separate target: PATCH the exact owned revision only. It never creates an API
# or changes the current revision. Default-off, never included by implication.
variable "auto_staging_take_offline" {
  type        = bool
  default     = false
  description = "Separately validated take-offline PATCH for the reserved noncurrent revision; no online transition."
}

resource "azapi_update_resource" "auto_stage_offline" {
  count       = var.auto_staging_take_offline && var.auto_staging_revision != null ? 1 : 0
  type        = "Microsoft.ApiManagement/service/apis@2024-05-01"
  resource_id = "${local.apim}/apis/aiflux-dev-unified;rev=${var.auto_staging_revision.revision}"
  body = { properties = {
    isOnline = false
  } }
  response_export_values = ["id", "properties"]
  lifecycle {
    prevent_destroy = true
    precondition {
      condition = (
        var.enabled && var.demo_authorized && var.persistent_poc_authorized &&
        var.allow_product_subscriptions && !var.candidate_validation &&
        !var.acceptance_verified && !var.auto_routing_enabled &&
        !var.poc_controls_enabled && !var.admin_settings_enabled &&
        local.api_name == "aiflux-dev-unified" && local.api_path == "dev/llm/v1"
      )
      error_message = "Take-offline only for the exact reserved noncurrent revision, all activation switches off; actual ownership/readback gates remain mandatory."
    }
  }
}