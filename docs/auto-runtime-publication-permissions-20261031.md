# Auto pool runtime publication: live permission verification

Observed 2026-10-31, closed at 23:15 SGT (15:15 UTC). Read-only Azure CLI/ARM and Microsoft Graph checks; no runtime managed-identity token or write probe.

## Scope and method

- Subscription: `aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`.
- Tenant: `beb276ac-6e9f-498e-8e31-019ee666decd`.
- Resource group: `IDS-TOKEN-EXCHANGE-POC`.
- Target policy: APIM `poc-ids-token-ex-apim`, API `aiflux-dev-unified`, policy `policy`.
- CLI account matched operator `xv.puneet.devadiga@singtel.com`; this operator is not the runtime publisher.
- Used the existing CLI and corporate CA with TLS verification enabled. Azure MCP CLI guidance returned HTTP 403; its troubleshooting guide was consulted, and installed CLI reads succeeded.
- Read deployed site identity attachments, selected non-secret API settings, managed identities, subscription assignments, literal target-scope inherited assignments, applicable role definitions, transitive memberships, and target-scope inherited deny assignments.
- Final site inventory returned no continuation link. Graph membership results and the deny-assignment result returned empty `value` arrays with no continuation link.
- One long terminal command was rejected by the PowerShell parser. Its intended results were not accepted as evidence; subsequent short standalone reads established the findings below. An earlier variable-based role query was likewise superseded by literal full-scope queries.

## Deployed runtime identity

API app `poc-ids-token-ex-api` is Running, with UserAssigned identity:

- Identity name: `poc-ids-token-ex-api-identity`.
- Client ID: `f0b3046c-dbf8-4d37-a4cf-65f2c7e6b4c1`.
- Principal ID: `4e7b70ed-9868-47ba-9b61-304f1e1fdd89`.
- Deployed `AZURE_CLIENT_ID` matches that client ID.
- Deployed `GATEWAY_PUBLICATION_WORKER_ENABLED` is `false`.

The identity `poc-ids-token-ex-control-plane-identity` exists:

- Client ID: `ea0a8eb4-039e-4f51-8c2f-f89ac3fc3a1c`.
- Principal ID: `967370eb-a5b0-4531-bc2b-b15a83ac3efd`.
- No control-plane App Service/Function site is deployed in this resource group. Complete site inventory contains only API, customer, admin, and ingestion. This does not claim that no other execution host exists elsewhere.

## Observed APIM grants

API identity has the following unconditional assignments:

1. `poc-ids-token-ex-subscription-manager`, definition `fa10dd61-c879-43e6-b259-384d4d29d452`, scoped to the APIM service. Actual Actions:
   - `Microsoft.ApiManagement/service/products/read`
   - `Microsoft.ApiManagement/service/read`
   - `Microsoft.ApiManagement/service/subscriptions/read`
   - `Microsoft.ApiManagement/service/subscriptions/write`
   - `Microsoft.ApiManagement/service/subscriptions/listSecrets/action`
   - `Microsoft.ApiManagement/service/subscriptions/regeneratePrimaryKey/action`
   - `Microsoft.ApiManagement/service/subscriptions/regenerateSecondaryKey/action`
2. `poc-ids-scoped-APIM-read-write-role`, definition `16ca19f5-170e-4549-a223-d6f3381a6ccf`, scoped only to fragment `aiflux-dev-unified-poc-settings`. Actual Actions:
   - `Microsoft.ApiManagement/service/policyFragments/read`
   - `Microsoft.ApiManagement/service/policyFragments/write`

Both definitions have empty NotActions, DataActions and NotDataActions. No wildcard grants occur in these definitions. The fragment assignment does not cover the API policy: they are different resource branches.

The literal API-policy inherited-assignment query returned only the subscription-manager role for the API principal and an empty array for the control-plane principal. Subscription-wide enumeration also found no APIM assignment for the control-plane principal. Their other enumerated assignments target ACR, Insights, logs, Storage or Key Vault resources and cannot cover this policy.

Microsoft Graph transitiveMemberOf returned no memberships for either principal. The target policy denyAssignments query with `atScope()` returned no entries. No role-assignment conditions appeared on the relevant observed grants.

## Verdict

**Neither checked identity has the required API-policy read/write grant in the observed effective assignment coverage.** Required Actions are:

- `Microsoft.ApiManagement/service/apis/policies/read`
- `Microsoft.ApiManagement/service/apis/policies/write`

This is live assignment evidence, not an inference from requested RBAC in Terraform. Full API-policy runtime publishing cannot be implemented under these existing grants. No roles were granted and no authorization failure was deliberately triggered using a PUT.

The API identity does have existing fragment read/write authorization. Metadata verification does not prove runtime token acquisition, networking or successful publication; none was exercised.

## Existing-permission alternative

Source inspection supports a separate design: retain Terraform ownership of invariant routing policy; make a one-time reviewed gateway change to consume a bounded Auto snapshot from the already-authorized POC settings fragment. The API can subsequently publish the typed snapshot through that fragment rather than updating the API policy.

Existing `GatewaySettingsRevision.configuration` stores JSON in a Text column. `save_poc()` already records a desired revision and calls `publish_poc()`, which performs ETag-protected fragment publication and strict readback. This is a reusable persistence/publication mechanism, not an existing Auto publisher. The background worker is disabled and is not required for the existing synchronous initial publish path.

Before implementation/release, this alternative still requires:

- Typed platform-wide pool state and schema/version compatibility; no arbitrary caller-supplied policy XML or expressions.
- Preservation of safety/quota fields across Auto, safety and gateway editors, including legacy payloads and shared revision concurrency.
- Verification of the fragment include order relative to Auto selection; current Auto code overwrites its snapshot with Terraform-embedded data.
- Measured whole-fragment UTF-8 size, including ownership bindings and maximum candidate descriptors; the renderer/client enforce 65,536 bytes. No unmeasured headroom estimate is accepted.
- Review of static candidate allowlists and current 2–10 choice validation before offering all 22 models.
- Concurrency, ambiguous-write readback, failure retention and Terraform ownership tests. Existing publication code must be audited rather than assumed to meet every new requirement.
- One-time narrowly reviewed gateway/application release under existing deployment authority, separate from runtime managed-identity rights.

No new subscription/model usage gates, identity, RBAC grant, secret, network change or DDL is implied. Explicit models remain independent of pool membership. This alternative is not implemented or deployed by this verification.

## Changes and non-actions

Only this evidence document was added. No application or gateway source, cloud resource, setting, database row or pricing record was changed. No keys were retrieved; no policy PUT/PATCH, deployment, build, inference or paid smoke test was performed. Existing live Auto was not modified or disabled.