# Existing revision2 take-offline: PATCH research and portal fallback

## Disposition — 2026-10-29

**Correction02 remains BLOCKED / NEVER APPLY. No successor saved plan was
produced or represented as reviewed. Portal fallback is waiting for interactive
user sign-in. No cloud configuration write or model invocation was performed
during this research.**

The official Azure portal was opened to the existing APIM service APIs blade
in tenant beb276ac-6e9f-498e-8e31-019ee666decd, subscription
aa28274d-fea0-46d4-b9c8-30f3ef0a0e52, resource group IDS-TOKEN-EXCHANGE-POC,
service poc-ids-token-ex-apim. The browser displayed **Sign in to Microsoft
Azure**, not an authenticated APIM blade. No login values, credentials, cookies,
tokens, or browser storage were extracted. The portal action was not attempted.

## Verified execution facts

These are source-level findings, not proof that the service accepts the body.

1. AzAPI **v2.13.0** `azapi_update_resource` reads and merges the resource,
   filters write-only properties, then calls `CreateOrUpdate`, which uses
   **HTTP PUT**. Correction02 cannot be described as a literal PATCH.
2. The same version's `azapi_resource_action` supports `method = "PATCH"`,
   empty `action`, exact `resource_id`, and explicit `headers`. Empty action
   leaves the resource URI unchanged. Without sensitive-body inputs, its body
   is passed directly to the action client, unlike update-resource filtering.
3. The exact **2024-05-01** API Swagger defines `Api_Update` as PATCH on the
   revision-capable API URI, with `ApiUpdateContract` and required If-Match.
   GET and HEAD expose ETag as an opaque conditional-request value.
   `ApiUpdateContract` inherits `ApiEntityBaseContract.isOnline`, which is
   explicitly `readOnly: true`. That annotation alone does not establish how
   a handwritten PATCH behaves on this service. No such PATCH was sent here.
4. Generic retries can be disabled with a dedicated provider's
   `maximum_busy_retry_attempts = -1`, provided no resource `retry` block
   overrides it. The exact dependency is azcore **v1.23.1**: zero means its
   default three retries; negative means one try and no generic retries.
   A non-null AzAPI resource retry block instead installs a 32767-retry budget.
5. **A separate automatic replay remains.** AzAPI installs
   `acquirePolicyTokenPolicy` as a per-call policy. After a qualifying 403 it
   can acquire a policy token, rewind the request body, and call `req.Next()`
   again. This path is outside the SDK retry budget.
   `always_acquire_policy_token = true` is not a guaranteed remedy: when
   proactive acquisition returns no usable token, the implementation falls
   back to the same reactive path. No supported disable switch was found in
   the inspected provider configuration. Fake policy-evaluation headers or
   tokens are not an acceptable workaround. RP registration would separately
   need to be disabled for a narrowly scoped provider.
6. Documented `Set-AzApiManagementApiRevision` parameters do not expose
   `-IsOnline`; that suggested command was not invented or attempted.

Therefore an action-resource plan could truthfully represent literal
PATCH + If-Match + false-only body, but the inspected provider cannot support
the requested **no automatic retries** guarantee without an unresolved
policy-token replay path. A plan with that known gap was not manufactured for
parent review. The explicitly authorized official portal fallback was used
instead and is now blocked only at interactive authentication.

## Source references inspected

- [AzAPI update resource v2.13.0](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/services/azapi_update_resource.go)
- [AzAPI action resource v2.13.0](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/services/azapi_resource_action_resource.go)
- [AzAPI resource HTTP client v2.13.0](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/clients/resource_client.go)
- [AzAPI client pipelines v2.13.0](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/clients/client.go)
- [AzAPI policy-token replay v2.13.0](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/clients/acquire_policy_token_policy.go)
- [AzAPI retry options v2.13.0](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/clients/options.go)
- [AzAPI provider options v2.13.0](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/internal/provider/provider.go)
- [AzAPI dependency versions v2.13.0](https://github.com/Azure/terraform-provider-azapi/blob/v2.13.0/go.mod)
- [azcore v1.23.1 retry options](https://github.com/Azure/azure-sdk-for-go/blob/sdk/azcore/v1.23.1/sdk/azcore/policy/policy.go)
- [azcore v1.23.1 retry defaults/execution](https://github.com/Azure/azure-sdk-for-go/blob/sdk/azcore/v1.23.1/sdk/azcore/runtime/policy_retry.go)
- [Exact APIM 2024-05-01 API operations](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/apimanagement/resource-manager/Microsoft.ApiManagement/ApiManagement/stable/2024-05-01/apimapis.json)
- [Exact APIM 2024-05-01 definitions](https://github.com/Azure/azure-rest-api-specs/blob/main/specification/apimanagement/resource-manager/Microsoft.ApiManagement/ApiManagement/stable/2024-05-01/definitions.json)
- [Official APIM revisions / take-offline documentation](https://learn.microsoft.com/en-us/azure/api-management/api-management-revisions)
- [Official PowerShell revision setter](https://learn.microsoft.com/en-us/powershell/module/az.apimanagement/set-azapimanagementapirevision)

GitHub blob pages were accessible; raw-content endpoints returned 403. The
Swagger hierarchy includes the additional `ApiManagement` directory. Earlier
404s from the old hierarchy are not evidence that the contract is absent.

## Continuation limits

- User signs in directly to the already-open official Azure portal. Never ask
  for credentials or MFA values in chat and never extract browser auth material.
- Before any take-offline action, freshly establish full13 and supplemental
  protected baseline, exact local state lineage/serial/bytes, remote state HEAD,
  worker/intent exclusivity, current revision1, and the original reservation
  nonce in the existing noncurrent revision2 description. Historical evidence
  is not a fresh safety check. This research did not refresh that baseline.
- Only use the normal portal take-offline operation on the verified owned
  revision2; do not make current, create/copy/delete a revision, change current
  API metadata, edit policy, or enable Auto. Resolve any newly displayed scope
  mismatch before continuing. Retain the actual UI result and fresh readback.
- Actual flat revision-list `isOnline=false`, `isCurrent=false`, unchanged
  current revision1 and all protected components are required for success.
  Neither provider state nor an HTTP success code alone is sufficient.
- No correction02/original-create replay, automatic restore, scoring,
  completions, image work, or role/identity/network changes.
- Parent-native independent review has not been invoked by this worker. No
  claim of new tests, Terraform validation, a fresh ETag, a successor saved-plan
  hash, service acceptance, or verified offline state is made.