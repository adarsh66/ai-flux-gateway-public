# Playground deployment inventory — 2026-10-26

## Current final status — 13:00–13:10 UTC

The checked source snapshot now has **eleven deployments and ten accepted
chat routes**, verified_at2026-10-26T12:44:49.521995+00:00. Each accepted route
is1024 tokens, chat-only and no expiry. All ten passed fresh direct HTTPS and
actual browser UI tests. Customer/admin active metadata sets equal the gateway
route manifest; auto is disabled and Decision-1 is routing-only/nonselectable.
See [current per-model acceptance and remaining release limitations](multimodel-acceptance-20261026.md).

The running deployment-metadata endpoint is404, unlike the newer local source.
Do not infer that the new inventory-aware runtime, audited sync operation or
deployment-status UI has been released merely because live database/catalog
readback is correct. The four-model/zero-route and absent-gateway statements
below are **historical phase evidence**, not current service state.

## Historical corrected target — superseded four-model snapshot

Observed **2026-10-26T04:25:19.545241Z** with the existing signed-in Azure CLI and
the supplied corporate CA, TLS verification enabled. The only current project is
https://poc-ids-token-ex-foundry.services.ai.azure.com/api/projects/poc-ids-token-ex-foundry-project.
Parent account: poc-ids-token-ex-foundry, subscription
aa28274d-fea0-46d4-b9c8-30f3ef0a0e52, RG IDS-TOKEN-EXCHANGE-POC. Parent and child
Succeeded; the project's ARM-advertised endpoint exactly matches. Connections:
successful complete empty list. Parent deployment list:4, no remaining pages.

| Exact deployment | Model version | Format | State | Capacity | Chat |
| --- | --- | --- | --- | ---: | --- |
| gpt-6.1-sol | 2026-09-29 | OpenAI | Succeeded | 5000 | Yes |
| gpt-5.6-luna | 2026-07-09 | OpenAI | Succeeded | 5000 | Yes |
| DeepSeek-V4-Flash | 2026-04-23 | DeepSeek | Succeeded | 2500 | Yes |
| Decision-1 (model Microsoft-Decision-1) | 1 | Microsoft | Succeeded | 250 | No |

DeploymentState was null for all4. Decision-1 is not a chat alias; its existence
does not configure auto routing. No gpt-5-mini/model-router/embedding entries from
the superseded account enter the current inventory. The
[snapshot](../gateway/catalog/foundry-inventory-20261026.json) is replaced with
these actual reads, still **routes:[]**. A succeeded deployment is not a passing
gateway test or legal acceptance.

The gateway's existing Cognitive Services User grant is on this correct parent
account and is inherited at project scope. No redundant role is requested.
Operator project deployment discovery still returns PermissionDenied; the
collector records that fact and uses the exact verified own-parent ARM fallback.
It is not gateway inference-denial evidence. See the
[current route correction](apim-route-repair-20261026.md) for the endpoint,
defaults, threshold0 incompatibility and actual404 bounded probe.

## Historical read-only evidence — WRONG TARGET, not runtime configuration

Everything in this historical inventory section through the source-fix heading
describes the superseded IDS-AI-Token project, not the user's corrected target.
The historical missing-permission discussion is not a current role request.

Observed **2026-10-26T03:47:36.129925Z** using the existing signed-in Azure CLI,
with the approved corporate CA bundle and TLS verification enabled. No inference
requests, resource provisioning, policy/gate updates, role grants, app-setting
changes, database migrations, or portal releases were performed.

- Project endpoint: https://ids-ai-token.services.ai.azure.com/api/projects/proj-poc-token-exchange
- Subscription: aa28274d-fea0-46d4-b9c8-30f3ef0a0e52
- Resource group: IDS-TOKEN-EXCHANGE-POC
- Parent account ID: /subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.CognitiveServices/accounts/IDS-AI-Token
- Project ID: parent account ID + /projects/proj-poc-token-exchange
- ARM account and project: `Succeeded`; the project's advertised endpoint exactly
  matches the endpoint above. Account region: southeastasia.
- Project connection list: successful, **zero connections**, no remaining pages.
- Parent deployment list: successful, five deployments, no remaining pages.
  Foundry MCP account deployment retrieval independently agrees with ARM.

| Exact deployment name | Provider model name | Version | Format | State | Capacity | Chat |
| --- | --- | --- | --- | --- | ---: | --- |
| gpt-5-mini | gpt-5-mini | 2025-08-07 | OpenAI | Succeeded | 5000 | Yes |
| model-router | model-router | 2025-11-18 | OpenAI | Succeeded | 250 | Yes |
| DeepSeek-V4-Flash | DeepSeek-V4-Flash | 2026-04-23 | DeepSeek | Succeeded | 5000 | Yes |
| gpt-5 | gpt-5 | 2025-08-07 | OpenAI | Succeeded | 15000 | Yes |
| text-embedding-3-small | text-embedding-3-small | 1 | OpenAI | Succeeded | 5000 | No |

All `deploymentState` values were null and `currentCapacity` matched capacity.
These are deployment resources, **not the public Foundry model catalog**. A
successful deployment is not proof of inference authorization, gateway acceptance,
health, context/output limits, pricing, or support for streaming/tools/JSON.

Exact deployment IDs, model/version mappings, timestamp and read provenance are
recorded in [the sanitized snapshot](../gateway/catalog/foundry-inventory-20261026.json).
This historical snapshot is **not activated as runtime configuration**.

### Precise missing permission

The SDK-documented project operation is
`GET {projectEndpoint}/deployments?api-version=v1`, audience `https://ai.azure.com`.
It returned **401 PermissionDenied**, explicitly identifying the missing data action:
`Microsoft.CognitiveServices/accounts/AIServices/deployments/read`.
The signed-in operator was successfully authenticated; this is not an empty list
and not a failed ARM deployment read. No additional permissions were granted.
The runtime managed identity was **not tested** for this data action; do not claim
it has or lacks it based on the operator's result.

The fallback is explicitly bounded to the ARM-verified project's own parent,
with a successful empty project connection list. Other RG accounts (including
IDS-AI-Token-Backup and poc-ids-token-ex-foundry) are not implicitly attached to
this project. A connection would not itself prove a successful deployment. The
collector currently rejects nonempty connections pending an explicitly scoped,
joined inventory implementation; it never silently includes their accounts.

References:
- [DeploymentsOperations.list](https://learn.microsoft.com/python/api/azure-ai-projects/azure.ai.projects.operations.deploymentsoperations?view=azure-python)
- [Foundry permission guidance](https://aka.ms/FoundryPermissions)
- [Azure MCP troubleshooting](https://aka.ms/azmcp/troubleshooting)

The exact REST path/audience were checked against the published azure-ai-projects
2.9.0 wheel's generated request builder; no SDK dependency was added. The required
Windows Foundry dependency script ran first. `azd` was initially missing; a local
official release download was attempted, but execution was blocked by Windows
group policy. The setup did not complete; read-only metadata verification used
the existing working Azure CLI instead. Azure best-practice guidance and MCP
discovery were consulted; transient MCP errors were checked against the guide.

## Source fix

Previously, PostgreSQL/local-auth `/api/models` fell back to enabled seeded
Model Garden rows even with `catalog_configured=false`. Those seeds still describe
the old six-model demo, unrelated endpoints and speculative capabilities. The
development catalog also refers to different accounts. Neither is live inventory.

[FoundryInventory](../services/control-plane/src/aiflux/foundry_inventory.py) now
requires an explicitly supplied, fresh inventory for both catalog sources:

1. Scope must match configured project endpoint/resource ID, parent account and
   deployment resource IDs. Duplicate aliases/IDs, incomplete reads, unknown
   provenance, future/naive timestamps, malformed/missing/expired files fail closed.
2. Only `Succeeded`, positive-capacity, non-disabled chat deployments qualify.
   Embeddings do not enter the chat playground.
3. A separately **gateway-validated** route must bind UI alias, exact deployment
   name (`backend_model`), provider model name/version and exact HTTPS backend base.
   Aliases may differ from deployment names; provider model IDs are never used as
  a guess for deployment names. A catalog with no pool uses this explicit route
  binding as its endpoint source. Every configured pool member must match; foreign
   endpoints or mixed models are excluded.
4. Existing enabled metadata must also match the binding. Metadata is not rewritten
   to pretend another model is equivalent. Advertised capabilities are intersected
   with accepted capabilities; completion limits are bounded by acceptance and the
   configured gateway limit. No new model pricing/context limits were invented.
5. Customer catalog/playground and customer Model Garden suppress unverified
   entries. Admin metadata remains inspectable but reports effective availability;
   toggling a SQL metadata flag cannot activate a deployment.
6. `auto` additionally requires an enabled router, exact accepted live auto route,
   valid default and verified candidate routes. The existing local heuristic may
   select only those candidates, never arbitrary seeded models or a hard-coded
   fallback. `model-router` existing in ARM does **not** establish this mapping,
   and is not evidence that Microsoft Decision-1 is configured for this project.
7. Server-side chat sends the exact accepted deployment model on the accepted
   OpenAI-compatible gateway route. Silent Claude-to-GPT substitutions and
   synthetic non-test success responses are removed. Unsupported wire formats are
   not guessed; an accepted translating gateway is required.

### Runtime configuration and refresh

- `AIFLUX_FOUNDRY_PROJECT_ENDPOINT` and `AIFLUX_FOUNDRY_PROJECT_RESOURCE_ID` now
  default together to poc-ids-token-ex-foundry / poc-ids-token-ex-foundry-project,
  never IDS-AI-Token. Old snapshot/project mismatches fail closed.
- `AIFLUX_FOUNDRY_INVENTORY_PATH` has **no default**. Supply a mounted/operator
  release artifact after review; missing reads return a sanitized HTTP 503.
- `AIFLUX_FOUNDRY_INVENTORY_MAX_AGE_SECONDS` defaults to **3600**, hard maximum
  **86400**. Refresh before expiry; no stale last-known-good fallback is used.
- Existing `AIFLUX_CATALOG_CONFIGURED` and inference gates remain unchanged.
- The runtime performs no ARM/Foundry network calls and needs no new read role.
  An authorized operator/release job is responsible for fresh evidence. This is a
  bounded snapshot, not continuous detection of deletes within the freshness window.

[The read-only collector](../gateway/tools/verify_foundry_inventory.py) accepts
`--project-endpoint`, `--project-resource-id`, and optional `--azure-cli` (the full
Windows CLI path is supported). It emits sanitized JSON to stdout, uses only GETs,
follows same-resource pages, never prints raw CLI errors/credentials, and always
emits `routes: []`. A read failure produces no usable artifact. Only the exact
project data-plane permission denial may retain explicit ARM-parent provenance;
other failures are not treated as successful inventory.

The route schema is in [RouteEvidence](../services/control-plane/src/aiflux/foundry_inventory.py).
An authorized future acceptance step must explicitly add `alias`, `deployment_id`,
`backend_model`, `model_name`, `model_version`, `endpoint_url`,
`api_format=openai-chat-completions`, accepted `capabilities`, bounded
`max_completion_tokens` and `gateway_validated=true`. The collector cannot attest
gateway validation. Refreshing deployments must not blindly preserve stale route
acceptance when model versions or endpoints change.

### Historical source-phase result and blockers (superseded)

At that earlier source phase the checked snapshot deliberately contained
**zero accepted route bindings** (it now contains ten).
Consequently the rebuilt source with no configured inventory returns 503; with
fresh evidence but no accepted routes it returns an empty callable catalog. It
does **not** falsely offer six old seed names or claim the corrected project's four deployments are
usable gateway routes. Publishing real chat choices requires approved metadata
and exact validated gateway bindings for this project, then a separately authorized
release. Do not mark the other account's development catalog accepted for this one.

The previously verified APIM `/dev/llm/v1` adapter is absent and inference gates
remain disabled; see [the CORS investigation](apim-cors-investigation-20261026.md).
No gateway readiness is attested by this inventory work. The live customer/admin
portals and their currently deployed model list remain **unchanged pending release**.

## Validation

- Original source baseline of the existing config/control-plane/dev-catalog/
  Turnstile tests: 37 passed, captured in-memory from Git without resetting work.
- **116 focused Python tests passed** (one existing dependency deprecation warning).
  Deployment-inventory regression cases cover scoped failures, expiry,
  embeddings, aliases vs provider IDs, failed/deactivated deployments, empty
  connections, acceptance, pools, caps, PostgreSQL fallback, router candidates and
  exact request mapping. Synthetic deployments are explicit test fixtures only.
- Customer/admin TypeScript typechecks passed. Vitest execution was attempted but
  blocked before tests by native esbuild `spawn UNKNOWN` under this Windows policy;
  no frontend execution pass is claimed. A broader Python run including the
  unchanged legacy portal-auth test is blocked at collection because it imports
  the removed `PortalUser` model; the 116-test run excludes that unrelated file.
  Editor baseline had only two
  pre-existing redirect-page viewport warnings; no owned diagnostics introduced.
- No concurrent CORS/Terraform/pipeline changes were altered by this task.