# APIM browser preflight investigation — 2026-10-26

## Authorized route-repair continuation

The later explicit repair request is tracked in
[the scoped repair record](apim-route-repair-20261026.md). Fresh live reads still
show the absent adapter; the actual remaining blockers are account-scoped gateway
MI inference permission, explicit model/cost/safety acceptance and verified
subscription budget/quota enforcement. A tested fail-closed repair planner and
exact-plan guard were added. **No live repair or completion success is claimed.**

## Follow-up: actual browser and direct API send verification

Rechecked **2026-10-26 03:58–03:59 UTC**. **Not fixed: neither the
signed-in playground nor the direct API test returned a completion.**

- Current ARM API list completed with only `v1` and `dev/v1`; the requested
  `dev/llm/v1` adapter remains absent. APIM reports `Succeeded` and public
  network access `Enabled`.
- Verified the existing Caldova-AI subscription ID matches the signed-in
  customer's subscription and is `active`. Retrieved its existing primary key
  into process memory for the authorized direct request; no credential files
  were read, no keys were rotated, and no secret was placed in CLI arguments
  or deliberately emitted by the API probe.
- At **03:59:24 UTC**, anonymous OPTIONS to
  `https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1/chat/completions`
  returned **404**, error code `404`, without `Access-Control-Allow-Origin`.
- One direct HTTP POST to that same endpoint, with the existing subscription
  key attached, bypassed browser CORS enforcement. Body: model `gpt-5-mini`,
  user message `Say hello.`, `max_completion_tokens: 16`, `stream: false`.
  It returned **404**, error code `404`, and **no completion**. No retry or
  redirect was followed. Supplying the key does not prove APIM validated it
  when the requested route is absent.
- At **03:59:47–03:59:48 UTC**, submitted `Say hello.` in the shared signed-in
  customer playground, using its selected `auto` model and Caldova-AI
  subscription. A temporary browser-only request cap limited output to 16
  tokens with streaming off. The browser rejected the preflight for missing
  `Access-Control-Allow-Origin`; the UI displayed **Network error — Could not
  reach the gateway. The request was not retried.** No assistant answer appeared.

The failure therefore persists outside browser CORS as well. Restoring the
reviewed, guarded adapter and its accepted backend/product bindings remains a
separate authorization boundary; adding an origin alone is insufficient.
Earlier global-policy gate findings below are historical: this follow-up could
not reread the policy and does not attest its current flag values. AppLens
again failed to create an APIM diagnostic session (`BadRequest`); successful
ARM metadata reads and actual HTTP responses provide the evidence above.
No Azure configuration, resource, RBAC, gate or deployment changes were made.

## Boundary and result

Read-only Azure inspection preceded source edits. No Terraform plan/apply,
policy PUT/PATCH, inference call, subscription-secret retrieval, app-setting
retrieval, role assignment, or Foundry activation was performed.

The reported signed-in browser uses
`https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1`, not the speculative
Application Gateway hostname. Reveal returning 200 establishes control-plane key
retrieval, not the existence or readiness of the APIM inference route.

**Current finding: the requested APIM route is absent, and the live development
inference gates are closed. This is not a verified disallowed-origin or
operation-level OPTIONS interception problem.** Missing CORS headers on that
404 are real, but adding an origin alone cannot make this playground work.

## Sanitized live evidence

Observed 2026-10-26 03:24–03:28 UTC, subscription
`aa28274d-fea0-46d4-b9c8-30f3ef0a0e52`, resource group
`IDS-TOKEN-EXCHANGE-POC`, service `poc-ids-token-ex-apim`.

ARM reads used the installed Azure CLI's full executable path and the supplied
combined corporate CA, with certificate verification enabled. APIM API version
was `2024-05-01`. Only whitelisted metadata and policy structure were printed;
no keys, tokens, passwords, app settings or inference content were printed.

| Check | Current response |
| --- | --- |
| APIM resource metadata | `Succeeded`; public network `Enabled`; VNet `None`; expected `azure-api.net` gateway URL |
| GET `/status-0123456789abcdef` | 200, empty body; gateway is reachable, not proof of inference readiness |
| OPTIONS `/dev/llm/v1/chat/completions`, customer origin | 404; no `Access-Control-Allow-*` headers |
| Same OPTIONS, untrusted origin | 404; no `Access-Control-Allow-*` headers |
| GET `/dev/llm/v1/models`, anonymous | 404 |
| OPTIONS `/dev/v1/chat/completions`, customer origin | 503; `gateway_unavailable`; no `Access-Control-Allow-*` headers |
| Customer `/` and `/healthz` | 200; ARM customer and API site metadata reports `Running` |

Preflight sent no subscription key or bearer token. Request headers were exactly:
`Origin: https://poc-ids-token-ex-customer.azurewebsites.net`,
`Access-Control-Request-Method: POST`, and
`Access-Control-Request-Headers: content-type,ocp-apim-subscription-key`.
The new anonymous diagnostic independently reproduced the 404 and 503 at
03:27:33 and 03:27:34 UTC respectively, with `passed: false` in both cases.

AppLens could not create an APIM diagnostic session (`BadRequest`); this is a
diagnostic limitation, not evidence of APIM authorization failure. Its customer
site diagnostic reported an older stopped worker; the current ARM reads and
successful HTTP probes above do not support treating that as this failure's cause.

## Exact live policy scopes and inheritance

All list responses below had no next page.

| Scope | Findings |
| --- | --- |
| Global `/policies/policy` | Inbound starts with `choose`; no CORS, no `base`; both development allow-path flags are literal `false`. Other paths are denied with 503. On-error maps missing/invalid subscription keys to 401 for the designated dev paths, otherwise 503. |
| API `aiflux-dev-unified`, path `/dev/llm/v1` | Absent from API list; API policy and operations reads both return `ResourceNotFound`. There is no API policy into which to insert CORS today. |
| API `aiflux-dev-openai`, path `/dev/v1` | Current revision 1; subscription required; no version/header-versioning configuration. Inbound immediately returns 503 `native_capability_unverified`; no CORS and no `base`. |
| API `aiflux-native-validation-pending`, path `/v1` | Current revision 1; subscription required; same disabled policy and no `base`. |
| Operations on both existing APIs | Only POST `/chat/completions` (`chat`) and GET `/models` (`models`). All four operation-policy GETs return `ResourceNotFound`; no explicit OPTIONS operation or operation-level override. |
| Products | Only `aiflux`; no product policy. No guarded development products are present. |
| Backends and APIM workspaces | Both lists empty. |

No operation policy replaces API inheritance. The existing disabled API policies
do not inherit global policies via `base`; their own 503 returns remain closed.
The enabled adapter **source**, in contrast, already places `cors` first and
then `base` before subscription/product/request/safety checks. There is no live
adapter CORS whose origin could currently be compared or reordered. The global
gate's position is not proven to be the cause of the absent-route 404.

Raw-export SHA-256 identifiers (GET with `format=rawxml`):

- Global: `fc043b134fe3d3cc1cada5472ec975240da4441ea6982776d077e64dba2a8171`
- Both disabled API policies:
  `a51f2fd903ab277257649d16d19eeb74c839a83ae39dc3f158c91d25e3e9cbfd`

The default XML export escapes policy expressions differently from raw export;
these hashes identify raw exports, not rendered Terraform file bytes.

## Source-only correction and exact diff

1. [../infra/terraform/dev-unified.tf](../infra/terraform/dev-unified.tf): change
   `cors_origins` from
   `distinct(concat(var.dev_portal_origins, [for h in [var.gateway_origin_hostname] : "https://${h}" if h != ""]))`
   to `var.dev_portal_origins`. Do not implicitly add a future edge hostname.
   Origin validation already requires distinct exact HTTPS App Service origins
   without paths/wildcards. No configuration values or enable flags were changed.
2. [../gateway/policies/dev-openai.xml.tftpl](../gateway/policies/dev-openai.xml.tftpl):
   add only a placement comment before the existing CORS block. Preserve its
   conditional `unified` rendering, first-inbound position, following `base`,
   `allow-credentials="false"`, and `terminate-unmatched-request="true"`.
   Methods remain GET/POST; allowed headers remain Content-Type and
   Ocp-Apim-Subscription-Key; exposed header remains Retry-After.
3. [../gateway/tools/probe_cors.py](../gateway/tools/probe_cors.py): add a separate
   OPTIONS-only CLI accepting `--base` and `--origin`. No Azure login or secrets
   are needed. It never follows redirects or submits an inference POST; it emits
   sanitized status/CORS metadata, distinguishing 404, 503, request interception,
   missing origins, missing POST/header permission, and overbroad CORS.
4. [../tests/contract/test_gateway_dev_policy.py](../tests/contract/test_gateway_dev_policy.py)
   and [../tests/contract/test_gateway_cors_probe.py](../tests/contract/test_gateway_cors_probe.py):
   cover placement, exact allowlists, no explicit OPTIONS operations, unchanged
   closed policies, anonymous request construction, redirect refusal, empty 200,
   wildcard/credential rejection, and 404/503 classification.

The intended browser origin is exactly
`https://poc-ids-token-ex-customer.azurewebsites.net`, not `/admin`, not a trailing
slash, not the APIM URL, not the Foundry project URL, and never `*`. The existing
guard requires both explicitly approved customer/admin portal origins before
adapter creation; this investigation does not relax that guard or invent inputs.

## Smallest live change and remaining approval boundary

**No CORS-only policy update is sufficient in the inspected live state.** Do not
add a global OPTIONS exemption or return a success-shaped preflight for a
nonexistent route, replace disabled policies with permissive forwarding, point
the browser directly at Foundry, or change the portal to `/dev/v1` (also closed).

For an already provisioned and approved adapter, the smallest CORS-only change
would be its single API-scoped policy: keep the narrow CORS block first, before
`base`, preserving every subsequent check. That policy does not currently exist.

Making this playground serve inference first requires a separately reviewed,
explicitly authorized restoration/configuration of the guarded `/dev/llm/v1`
API, its approved product/bindings, verified backends and prerequisite evidence,
and the corresponding global release gate. Do not merely toggle the flags.
The supplied target project is
`https://ids-ai-token.services.ai.azure.com/api/projects/proj-poc-token-exchange`;
its current deployments, model aliases, MI access, safety and routing readiness
were not attested by these APIM/preflight checks. Do not substitute historical
catalog aliases or treat a displayed `auto`/model list as backend readiness.
No Foundry activation or RBAC change is proposed or authorized here.

After any separately approved live change, re-read all policy scopes, verify the
approved origins and an untrusted origin, then verify authenticated error CORS
and a bounded completion with an approved subscription held only in memory.
Only that later evidence can establish a working signed-in browser journey.

## Validation

- Before edits: 16 existing development-policy contract tests passed.
- Focused policy/probe/adapter-verifier suite: **43 passed**.
- Full contract suite: **78 passed, 9 failed, 55 errors**. Replacing reads of
  the two changed pre-existing policy/Terraform sources with their Git HEAD
  contents in memory only, and excluding the 24 new test cases, reproduced the
  same nine failures and 55 errors (**54 passed**). No working files were
  reverted. These existing failures concern normalization, public deployment,
  and managed-settings contracts, including missing managed policy templates;
  no broader contract-suite success is claimed.
- Terraform formatting check for the changed file and Terraform validation both
  passed. Validation emitted the existing trusted provider-development-override
  warning; no plan or apply was run.
- Editor diagnostics for modified source/tests: clear.
- Ruff execution is blocked by Windows group policy (WinError 1260); no lint
  success is claimed.
- Scoped diff whitespace check passed. Whole-workspace check finds a pre-existing
  final blank line in the concurrently modified disabled Terraform tests;
  that file was not edited.

References: [Microsoft CORS policy semantics](https://learn.microsoft.com/azure/api-management/cors-policy)
and [policy export format](https://learn.microsoft.com/rest/api/apimanagement/policy/get?view=rest-apimanagement-2024-05-01).
The Azure AI Gateway skill and installed Azure MCP general best-practices command
were consulted; the latter returned status 200 via its installed executable.