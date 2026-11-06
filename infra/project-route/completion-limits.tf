# Optional successor input. No historical inventory or smoke receipt is edited.
# Package the exact same public JSON bytes at AIFLUX_GATEWAY_COMPLETION_LIMITS_PATH.
variable "completion_limits_path" {
  type        = string
  default     = ""
  description = "Reviewed release JSON: schema=1, allowance, exact provider_limits map. Configuration is not provider/safety verification."
  validation {
    condition = var.completion_limits_path == "" ? var.completion_token_limit <= 1024 : try(
      length(filebase64(var.completion_limits_path)) <= 21844 &&
      file(var.completion_limits_path) == jsonencode(jsondecode(file(var.completion_limits_path))) &&
      jsondecode(file(var.completion_limits_path)).schema == 1 &&
      jsondecode(file(var.completion_limits_path)).allowance == var.completion_token_limit &&
      toset(keys(jsondecode(file(var.completion_limits_path)))) == toset(["schema", "allowance", "provider_limits"]) &&
      toset(keys(jsondecode(file(var.completion_limits_path)).provider_limits)) == toset(local.all_aliases) &&
      alltrue([for limit in values(jsondecode(file(var.completion_limits_path)).provider_limits) :
    limit == tonumber(limit) && limit >= 1 && limit <= 1000000 && floor(limit) == limit]), false)
    error_message = "Output above1024 requires the same bounded exact-alias provider-limit contract in project-route and API; provider/full-output safety review is still required."
  }
}

locals {
  completion_contract = var.completion_limits_path == "" ? null : try(jsondecode(file(var.completion_limits_path)), null)
  effective_completion_limits = { for alias in local.all_aliases : alias => min(
    var.completion_token_limit,
    var.completion_limits_path == "" ? var.completion_token_limit : try(local.completion_contract.provider_limits[alias], 1)
  ) }
  auto_completion_version = var.completion_limits_path == "" ? local.auto_version : sha256("${local.auto_version}:${filesha256(var.completion_limits_path)}")
}