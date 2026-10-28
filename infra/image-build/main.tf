# Build-only root. Never manages the registry, applications, identities or grants.
# Initialize with the existing Entra-authenticated backend and a NEW release key.
terraform {
  required_version = "= 1.12.1"
  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "= 2.13.0"
    }
  }
  backend "azurerm" {}
}

provider "azapi" {
  subscription_id = "aa28274d-fea0-46d4-b9c8-30f3ef0a0e52"
  tenant_id       = "beb276ac-6e9f-498e-8e31-019ee666decd"
  use_cli         = true
}

variable "release_tag" {
  type = string
  validation {
    condition     = can(regex("^local-[0-9]{8}t[0-9]{6}z-[a-f0-9]{12}$", var.release_tag))
    error_message = "Use a fresh UTC timestamp and source-hash release tag, not a mutable channel."
  }
}

variable "build_enabled" {
  type    = bool
  default = false
}

locals {
  registry_id = "/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.ContainerRegistry/registries/pocidstokenexacr"
  images = {
    api                    = "services/control-plane/Dockerfile"
    admin                  = "apps/admin-portal/Dockerfile"
    customer               = "apps/customer-portal/Dockerfile"
    ingestion              = "services/usage-ingestion/Dockerfile"
    control-plane-function = "services/control-plane/functions.Dockerfile"
  }
}

# Issuing upload authorization is also Terraform-controlled. The source archive
# transfer itself is an application-artifact PUT, not Azure resource provisioning.
resource "azapi_resource_action" "source_upload" {
  type                   = "Microsoft.ContainerRegistry/registries@2019-06-01-preview"
  resource_id            = local.registry_id
  action                 = "listBuildSourceUploadUrl"
  method                 = "POST"
  body                   = {}
  response_export_values = ["relativePath", "uploadUrl"]
}

resource "azapi_resource_action" "build" {
  for_each    = var.build_enabled ? local.images : {}
  type        = "Microsoft.ContainerRegistry/registries@2019-06-01-preview"
  resource_id = local.registry_id
  action      = "scheduleRun"
  method      = "POST"
  body = {
    type               = "DockerBuildRequest"
    sourceLocation     = azapi_resource_action.source_upload.output.relativePath
    dockerFilePath     = each.value
    imageNames         = ["aiflux-${each.key}:${var.release_tag}"]
    isPushEnabled      = true
    noCache            = true
    timeout            = 3600
    platform           = { os = "Linux", architecture = "amd64" }
    agentConfiguration = { cpu = 2 }
    arguments = !contains(["admin", "customer"], each.key) ? [] : [
      { name = "VITE_AUTH_MODE", value = "local", isSecret = false },
      { name = "VITE_CONTROL_API_URL", value = "/api", isSecret = false },
      { name = "VITE_GATEWAY_URL", value = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1", isSecret = false },
    ]
  }
  response_export_values = ["properties.runId", "properties.status"]
  timeouts {
    create = "65m"
  }
}

output "source_upload" {
  value     = azapi_resource_action.source_upload.output
  sensitive = true
}

output "build_runs" {
  value = { for name, run in azapi_resource_action.build : name => run.output.properties }
}