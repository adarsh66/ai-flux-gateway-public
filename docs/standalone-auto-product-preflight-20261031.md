# Standalone Auto: actual fixed-product preflight

## Completed actual API test — 2026-10-31 14:29:48 UTC

**PASS: actual gateway HTTP 200; arithmetic response `4`.**

Supported Azure CLI `account get-access-token --scope
https://management.azure.com/.default` acquired a usable credential from the
existing session. Tenant, operator, and ARM audience matched; token lifetime at
the new stage was **2,380.27 seconds**, exceeding the unchanged 900-second guard.
Interactive login was unnecessary. No credential cache editing or TLS bypass.

All five prior standalone reports had zero sends, with no inference intents or
responses found. A new exclusive, fsynced wire ledger preceded the only gateway
POST. Retained full-guard evidence was referenced, not replayed; the fixed
product-scoped subscription was freshly read and confirmed active before the
established authorized in-memory `listSecrets` read. Publication was not changed.

- Request: `model=auto`, `routing_profile=balanced`, `stream=false`,
	`max_completion_tokens=32`; prompt: “What is 2 + 2? Reply with only the number.”
- Actual selected model: **DeepSeek-V4-Flash**; fallback **false**; finish **stop**.
- Completion usage: **18 prompt + 2 completion = 20 total tokens**.
- Decision usage: **4,255 input / 1 output tokens**; decision latency **1,464.5567 ms**.
- Exactly **one** gateway transport invocation; **zero** retries or redirects;
	remaining allowance **0**. Do not replay.
- No cloud configuration writes, publication writes, persisted keys, or persisted
	bearer tokens. Original source and receipt remain unchanged.
- This verifies the actual API response; no new full postguard run or delayed
	telemetry-ingestion verification was performed.

Evidence: [final report](../.deployment/auto-additive-buildplan01/standalone-api-fresh07/REPORT.json),
[sanitized actual response](../.deployment/auto-additive-buildplan01/standalone-api-fresh07/response.json),
[safe auth metadata](../.deployment/auto-additive-buildplan01/standalone-api-fresh07/auth-metadata.json),
[exclusive wire ledger](../.deployment/auto-additive-buildplan01/standalone-auto-wire-ledger.json).

The earlier preflight stops below are preserved history, superseded by this
completed actual test.

## Semantic correction and new authorized execution — 2026-10-31

**Correction:** the earlier publication prerequisite below was mistaken. APIM
`notPublished` controls developer-portal discovery; it does not revoke an existing
active product-scoped subscription. Microsoft documents that the product's APIs
remain accessible through the gateway regardless of publication:
[Create and publish a product](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-add-products).
Publishing the product is neither necessary nor authorized. Historical scripts and
receipts are preserved, not rewritten.

A new helper removed that extra eligibility condition while retaining the fixed
subscription, exact scope, all-22/Auto policy binding, original Client, pinned CA,
full read-only guards, one exclusive before-wire intent, and no retry/redirect.
Offline syntax, module binding, original hashes, and error-redaction checks passed.

**Actual new execution:** 14:24:23–14:24:27 UTC stopped during the first ARM
credential validation, before subscription-key retrieval or inference intent.
The credential subprocess succeeded, but the established full guard rejected its
token metadata. A single metadata-only check at 14:25:48 UTC confirmed:

- Tenant, operator, and ARM audience all match the established identity.
- Token remaining lifetime: **384.273 seconds**.
- Existing full-guard minimum **>600 seconds**: failed.
- Original inference Client minimum **>900 seconds**: failed.
- No forced refresh, lifetime relaxation, alternate authentication, or gateway retry.

**Actual return:** `PREFLIGHT_STOP_NOT_SENT`; gateway HTTP response and arithmetic
completion are **not available because no POST occurred**. Original paid requests
remain **0**, new gateway requests **0**, and the one paid-request allowance is
**unspent**, not a failed/unknown paid inference. No product/configuration/network/
role/DDL writes occurred. No secrets or raw credential responses were retained.

New evidence:
- [New helper](../.deployment/auto-additive-buildplan01/standalone-api-authorized06.py)
- [Actual execution report](../.deployment/auto-additive-buildplan01/standalone-api-authorized06/REPORT.json)
- [Safe token identity/lifetime metadata](../.deployment/auto-additive-buildplan01/standalone-api-authorized06/auth-metadata.json)

Stopped for parent review rather than weakening established authentication guards.
The older “Required resolution” section is historical and superseded by this
correction; **do not publish the product**.

## Actual result — 2026-10-31 14:20:47 UTC

**BLOCKED_NOT_SENT: GENUINE_PRODUCT_UNPUBLISHED_HTTP_200_NOT_PUBLISHED**

- Fixed APIM subscription: `e9f2abb0-930b-598a-b210-0ab0b279127f`.
- Subscription ARM GET: **HTTP 200**, state **active**.
- Subscription scope exactly matches the configured APIM product `/products/aiflux`.
- Product ARM GET: **HTTP 200**, API version **2024-05-01**, state **notPublished**.
- Product response resource ID and product name match the exact requested scope.
- No doubled `/products/products/` segment. This is not a 403, 404, 429, malformed product path, or malformed publication-state response.
- No publication change, alternate subscription, roles, security changes, DDL, or other cloud mutation performed.

## Actual request ledger

- Gateway transport invocations: **0**.
- Subscription key retrieved: **false**.
- Paid failed or unknown inference attempts: **0**.
- The original reservation was local preflight only; it is not evidence that scoring or completion occurred.
- The originally authorized one POST was **not sent** because the genuine publication prerequisite failed. No inference retry, replay, or fallback subscription was used.
- No exclusive inference intent was created because the inference eligibility gate did not pass. Any future authorized send must acquire an exclusive durable intent before the wire call; this report is not permission to replay anything.

## Durable evidence

- [Original immutable receipt](../.deployment/auto-additive-buildplan01/standalone-api-attempt02/REPORT.json)
- [Actual correction report](../.deployment/auto-additive-buildplan01/standalone-api-readonly05/REPORT.json)
- [Subscription HTTP metadata](../.deployment/auto-additive-buildplan01/standalone-api-readonly05/subscription-http.json)
- [Product HTTP metadata](../.deployment/auto-additive-buildplan01/standalone-api-readonly05/product-http.json)
- [Product identity and publication state](../.deployment/auto-additive-buildplan01/standalone-api-readonly05/product-state.json)

Original receipt SHA-256: `bfe25fd5ad8bf7102aef21478cce7d312950b803c72a701a6b06abc9d433af7a`, rechecked unchanged after the actual reads. Original script was not edited.

The retained full guards passed at 14:15:40 UTC (root serial 132, child serial 193); they were approximately five minutes old at the actual read-only investigation and were not repeated.

The first correction stopped locally on the existing client's 900-second token-lifetime threshold. A same-identity, same-audience, strict pinned-CA read-only client required 300 seconds for two bounded read operations, with retries and redirects disabled. The subsequent local helper-binding failure made no ARM or gateway request. All earlier receipts remain unchanged. Actual read-only results are exclusively in readonly05. Tokens and keys were not logged or persisted; arbitrary ARM response bodies were not retained.

## Required resolution

Publishing this genuinely unpublished product would require a separately authorized cloud write. No such write was authorized or attempted. The actual model API test therefore remains blocked and unperformed, not successful and not a consumed paid attempt.