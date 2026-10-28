# No secret values, secret data sources or role/network mutations in this module.
# The rotated value is provisioned out-of-band after resolver connectivity review.
variable "glm_enabled" {
  type    = bool
  default = false
}

variable "glm_credential_storage" {
  type        = string
  default     = "apim-internal"
  description = "Explicit reviewed storage mode. Internal encrypted secret is created OUTSIDE Terraform."
  validation {
    condition     = contains(["apim-internal", "key-vault"], var.glm_credential_storage)
    error_message = "Select the reviewed apim-internal or key-vault storage mode."
  }
}

variable "glm_internal_secret_verified" {
  type        = bool
  default     = false
  description = "Fresh metadata-only proof: fixed pre-existing named value has secret=true and no keyVault; not inference acceptance."
}

variable "glm_secret_identifier" {
  type        = string
  default     = ""
  description = "Reviewed existing versionless vault URI only; never the credential."
  validation {
    condition     = var.glm_secret_identifier == "" || can(regex("^https://[a-z0-9-]+\\.vault\\.azure\\.net/secrets/glm-5-3-api-key$", var.glm_secret_identifier))
    error_message = "Use an existing versionless Key Vault identifier for glm-5-3-api-key."
  }
}

variable "glm_resolver_verified" {
  type        = bool
  default     = false
  description = "Operator proof of actual APIM system identity, vault RBAC and control-plane refresh; not an inferred permission grant."
}

locals {
  glm_backend = "aiflux-external-glm-5-3"
  glm_aliases = var.glm_enabled ? ["glm-5.3"] : []
  all_aliases = concat(sort(keys(local.routes)), local.glm_aliases)
  glm_auth    = <<-XML
    <choose>
      <when condition='@((string)context.Variables["aiflux-model"] == "glm-5.3")'>
        <set-backend-service backend-id="${local.glm_backend}" />
        <rewrite-uri template="/chat/completions" copy-unmatched-params="false" />
        <!-- Inject only after all inbound safety/PII calls. Never use Foundry MI here. -->
        <set-header name="Authorization" exists-action="override"><value>Bearer {{aiflux-glm-5-3-api-key}}</value></set-header>
      </when>
      %{if length(local.fireworks_aliases) > 0~}
      <when condition='@(${join(" || ", [for alias in local.fireworks_aliases : "(string)context.Variables[\"aiflux-model\"] == \"${alias}\""])})'>
        <authentication-managed-identity resource="https://ai.azure.com" client-id="${local.gateway_client}" ignore-error="false" />
      </when>
      %{endif~}
      <otherwise><authentication-managed-identity resource="https://cognitiveservices.azure.com/" client-id="${local.gateway_client}" ignore-error="false" /></otherwise>
    </choose>
  XML
  # Preserve the shared legacy template and all its existing consumers. This
  # isolated replacement matches only the final inference authentication node.
  glm_auth_anchor    = "        <authentication-managed-identity resource=\"https://cognitiveservices.azure.com/\" client-id=\"${local.gateway_client}\" ignore-error=\"false\" />\n      </when>"
  glm_clean_headers  = join("", [for header in ["x-api-key", "apikey", "x-goog-api-key", "x-auth-token", "Proxy-Authorization", "Cookie", "Ocp-Apim-Trace", "Ocp-Apim-Trace-Location", "Apim-Debug-Authorization", "x-ms-client-request-id", "anthropic-version"] : "<set-header name=\"${header}\" exists-action=\"delete\" />"])
  glm_inbound        = var.glm_enabled ? replace(local.quota_policy, local.glm_auth_anchor, "${local.glm_clean_headers}${local.glm_auth}\n      </when>") : local.quota_policy
  glm_response_guard = <<-XML
    <choose><when condition='@((string)context.Variables.GetValueOrDefault&lt;string&gt;("aiflux-model", "") == "glm-5.3")'>
      <!-- No provider errors, redirects, cookies, challenge or diagnostic headers escape. -->
      <set-header name="Location" exists-action="delete" />
      <set-header name="Set-Cookie" exists-action="delete" />
      <set-header name="WWW-Authenticate" exists-action="delete" />
      <set-header name="Authorization" exists-action="delete" />
      <set-header name="api-key" exists-action="delete" />
      <set-header name="x-api-key" exists-action="delete" />
      <choose><when condition='@(context.Response.StatusCode != 200)'>
        <return-response><set-status code="503" reason="External model unavailable" />
          ${local.error_cors}
          <set-header name="Content-Type" exists-action="override"><value>application/json</value></set-header>
          <set-header name="Cache-Control" exists-action="override"><value>no-store</value></set-header>
          <set-body>{"error":{"code":"external_model_unavailable","message":"External model unavailable; no fallback or retry was attempted."}}</set-body>
        </return-response>
      </when></choose>
      <set-body id="aiflux-external-response"><![CDATA[@{
        var body = context.Response.Body.As<JObject>(preserveContent: true);
        var usage = body["usage"] as JObject;
        var choices = body["choices"] as JArray;
        var maximum = (int)JObject.Parse((string)context.Variables["aiflux-request-json"])["max_completion_tokens"];
        if (usage == null || choices == null || choices.Count != 1 ||
            usage["prompt_tokens"] == null || usage["prompt_tokens"].Type != JTokenType.Integer ||
            usage["completion_tokens"] == null || usage["completion_tokens"].Type != JTokenType.Integer ||
            usage["total_tokens"] == null || usage["total_tokens"].Type != JTokenType.Integer) {
          throw new Exception("Invalid external response");
        }
        var finishReason = (string)choices[0]["finish_reason"];
        if (finishReason != "stop" && finishReason != "length") {
          throw new Exception("Invalid external response");
        }
        var prompt = (long)usage["prompt_tokens"];
        var completion = (long)usage["completion_tokens"];
        if (prompt < 0 || completion < 1 || completion > maximum || prompt > int.MaxValue - completion ||
            (long)usage["total_tokens"] != prompt + completion || (string)body["model"] != "glm-5.3" ||
            (string)choices[0]["message"]["role"] != "assistant" ||
            choices[0]["message"]["content"].Type != JTokenType.String ||
            string.IsNullOrWhiteSpace((string)choices[0]["message"]["content"])) {
          throw new Exception("Invalid external response");
        }
        return new JObject {
          ["id"] = context.RequestId.ToString(), ["object"] = "chat.completion",
          ["created"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(), ["model"] = "glm-5.3",
          ["choices"] = new JArray(new JObject { ["index"] = 0,
            ["message"] = new JObject { ["role"] = "assistant", ["content"] = (string)choices[0]["message"]["content"] },
            ["finish_reason"] = finishReason }),
          ["usage"] = new JObject { ["prompt_tokens"] = prompt, ["completion_tokens"] = completion, ["total_tokens"] = prompt + completion }
        }.ToString();
      }]]></set-body>
    </when></choose>
  XML
  glm_response_final = <<-XML
    <choose><when condition='@((string)context.Variables.GetValueOrDefault&lt;string&gt;("aiflux-model", "") == "glm-5.3")'>
      <!-- After output safety, create a fresh response: no upstream headers survive. -->
      <set-variable name="aiflux-external-answer" value='@(context.Response.Body.As&lt;string&gt;(preserveContent: true))' />
      <return-response><set-status code="200" reason="OK" />
        ${local.error_cors}
        <set-header name="Content-Type" exists-action="override"><value>application/json</value></set-header>
        <set-header name="Cache-Control" exists-action="override"><value>no-store</value></set-header>
        <set-header name="x-aiflux-request-id" exists-action="override"><value>@(context.RequestId.ToString())</value></set-header>
        <set-body>@((string)context.Variables["aiflux-external-answer"])</set-body>
      </return-response>
    </when></choose>
  XML
  glm_outbound       = var.glm_enabled ? replace(local.glm_inbound, "<outbound>\n    <base />", "<outbound>\n    <base />${local.glm_response_guard}") : local.glm_inbound
  glm_policy         = var.glm_enabled ? replace(local.glm_outbound, "</outbound>", "${local.glm_response_final}</outbound>") : local.glm_outbound
}

resource "azapi_resource" "glm_named_value" {
  # Only the optional Key Vault REFERENCE may be managed. Never import the
  # internal secret, use a secret data source, or export its value into state.
  count     = var.enabled && var.glm_enabled && var.glm_credential_storage == "key-vault" ? 1 : 0
  type      = "Microsoft.ApiManagement/service/namedValues@2024-05-01"
  parent_id = local.apim
  name      = "aiflux-glm-5-3-api-key"
  body = { properties = {
    displayName = "aiflux-glm-5-3-api-key"
    secret      = true
    keyVault    = { secretIdentifier = var.glm_secret_identifier }
  } }
  lifecycle {
    precondition {
      condition     = var.glm_resolver_verified && var.glm_secret_identifier != "" && var.persistent_poc_authorized
      error_message = "GLM stays disabled until actual system-identity vault resolution is proven and persistent controls are preserved."
    }
  }
}

resource "azapi_resource" "glm_backend" {
  count     = var.enabled && var.glm_enabled ? 1 : 0
  type      = "Microsoft.ApiManagement/service/backends@2024-05-01"
  parent_id = local.apim
  name      = local.glm_backend
  body = { properties = {
    protocol = "http"
    url      = "https://api-ap-southeast-1.modelarts-maas.com/v1"
    tls      = { validateCertificateChain = true, validateCertificateName = true }
  } }
  lifecycle {
    precondition {
      condition = var.persistent_poc_authorized && (var.glm_credential_storage == "apim-internal" ? (
        var.glm_internal_secret_verified && var.glm_secret_identifier == "" && !var.glm_resolver_verified
        ) : (
        var.glm_resolver_verified && var.glm_secret_identifier != "" && !var.glm_internal_secret_verified
      ))
      error_message = "GLM requires reviewed storage-specific readiness; internal mode never owns or reads a secret in Terraform."
    }
  }
}