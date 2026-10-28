# Exact existing Fireworks deployments only. No roles, secrets or model writes.
resource "azapi_resource" "fireworks_backend" {
  count     = var.enabled && length(local.fireworks_aliases) > 0 ? 1 : 0
  type      = "Microsoft.ApiManagement/service/backends@2024-05-01"
  parent_id = local.apim
  name      = local.fireworks_backend
  body = { properties = {
    protocol = "http", url = local.fireworks_url
    tls      = { validateCertificateChain = true, validateCertificateName = true }
  } }
  lifecycle {
    precondition {
      condition     = var.persistent_poc_authorized && !var.poc_controls_enabled && var.glm_enabled && var.allow_product_subscriptions
      error_message = "Fireworks addition requires the unchanged product-authenticated POC with external GLM and optional controls OFF."
    }
  }
}