variable "model_access_enabled" {
  type        = bool
  default     = false
  description = "Enforce organization model access only after complete trusted binding bootstrap and reviewed native validation."
}

variable "model_access_bootstrap_sha256" {
  type        = string
  default     = ""
  description = "Exact raw-file SHA256 of reviewed bootstrap receipt. Hash shape alone is never activation proof."
}

variable "model_access_bootstrap_receipt_path" {
  type    = string
  default = ""
}

variable "model_access_receipt_python" {
  type        = string
  default     = "python"
  description = "Reviewed interpreter with the current control-plane package installed; validator is offline only."
}

data "external" "model_access_receipt" {
  count   = var.model_access_enabled ? 1 : 0
  program = [var.model_access_receipt_python, "-B", "-m", "aiflux.model_access_bootstrap", "terraform-validate"]
  query = {
    receipt_path   = abspath(var.model_access_bootstrap_receipt_path)
    receipt_sha256 = var.model_access_bootstrap_sha256
    root           = abspath("${path.module}/../..")
    target         = local.apim
    product        = "aiflux"
    aliases        = jsonencode(sort(distinct(concat(keys(local.routes), var.glm_enabled ? [local.glm_alias] : []))))
  }
}

locals {
  model_access_anchor = "        <set-variable name=\"aiflux-model\" value='@((string)JObject.Parse((string)context.Variables[\"aiflux-request-json\"])[\"model\"])' />"
  model_access_guard = templatefile("${path.module}/../../gateway/policies/model-access.xml.tftpl", {
    fragment = local.poc_fragment_name
    aliases  = join(", ", [for alias in sort(distinct(concat(keys(local.routes), var.glm_enabled ? [local.glm_alias] : []))) : "\"${alias}\""])
  })
  model_access_policy = var.model_access_enabled ? replace(local.foundry_eight_policy,
    local.model_access_anchor, "${local.model_access_anchor}\n${local.model_access_guard}") : local.foundry_eight_policy
}

check "model_access_bootstrap" {
  assert {
    condition = !var.model_access_enabled || (
      var.allow_product_subscriptions && !var.poc_controls_enabled &&
      can(regex("^[0-9a-f]{64}$", var.model_access_bootstrap_sha256)) &&
      try(data.external.model_access_receipt[0].result.valid == "true", false) &&
      length(split(local.model_access_anchor, local.foundry_eight_policy)) == 2
    )
    error_message = "Entitlements require complete reviewed bootstrap, product auth, detached controls and exactly one post-model-parse guard location."
  }
}