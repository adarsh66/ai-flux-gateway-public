# Ten-model current acceptance — 2026-10-26

## Final current result

**All ten chat deployments passed direct secure HTTPS and actual signed-in
customer browser select-and-send tests.** Every request used
`max_completion_tokens=1024`, `stream=false`, and the harmless prompt
“Reply with exactly OK.” All returned HTTP200, nonempty assistant text and
`finish_reason=stop`; the browser rendered Completed. No automatic inference
retry, quota reset, route mutation, Terraform apply or application deployment
was performed during this verification.

Gateway: https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1

Customer: https://poc-ids-token-ex-customer.azurewebsites.net/playground

### Per-model results

UTC times below are all on 2026-10-26. Direct tests ran13:04:31–13:04:58.
Browser checks ran13:00:30–13:03:43; these were real UI interactions and their
actual network responses, not direct fetches labeled as browser UI tests.

| Requested deployment | Direct HTTPS | Browser UI | Browser UTC | Browser completion / reasoning tokens |
| --- | --- | --- | --- | --- |
| gpt-5.6-luna |200, visible text, stop|200, Completed|13:03:29|4 / 0|
| gpt-6.1-sol |200, visible text, stop|200, Completed|13:03:39|4 / 0|
| gpt-5.4-mini |200, visible text, stop|200, Completed|13:03:30|4 / 0|
| gpt-4o |200, visible text, stop|200, Completed|13:03:37|1 / 0|
| DeepSeek-V4-Flash |200, visible text, stop|200, Completed|13:03:32|3 / not separately reported|
| DeepSeek-V4-Pro |200, visible text, stop|200, Completed|13:03:34|2 / not separately reported|
| Kimi-K2.7-Code |200, visible text, stop|200, Completed|13:01:53|24 / not separately reported|
| grok-4.3 |200, visible text, stop|200, Completed|13:01:05|1 / 140|
| grok-4-20-reasoning |200, visible text, stop|200, Completed|13:00:30|1 / 105|
| grok-4-1-fast-reasoning |200, visible text, stop|200, Completed|13:03:43|1 / 169|

Provider response identities matched the requested family/version. In particular,
Grok4-20 reports `grok-4.20-beta-0309-reasoning`; this is recorded, not rewritten
to the deployment alias. GPT identities include their version dates. The direct
Grok4.3/4-20/fast requests separately reported392/195/271 reasoning tokens.
Provider usage schemas differ: do not subtract Grok reasoning from its reported
one completion token or interpret absent reasoning fields as zero. This confirms
bounded visible responses, not guaranteed success for arbitrary1024-token prompts.
No429 occurred in these fresh tests.

Sanitized durable evidence:
[gateway/validation/multimodel-acceptance-20261026.json](../gateway/validation/multimodel-acceptance-20261026.json).
Full current direct metrics are retained locally in
[.deployment/project-models-current-1024-api.json](../.deployment/project-models-current-1024-api.json).
The earlier32-token probe artifacts remain historical; they were not overwritten
or used as current all-model evidence.

## Catalog and admin synchronization: actual API proof

At13:05:54 admin and13:06:55 customer, the signed-in browser captured actual
API responses and made authenticated read-only metadata reads using the existing
session only in memory. No key, bearer token or raw header values were printed
or saved. This is backend-response evidence, not a dropdown-only UI workaround.

- APIM `GET /dev/llm/v1/models`:200, exactly ten deployment aliases.
- Customer `GET /api/models`:200, eleven entries: **ten enabled,
  nonplaceholder chat entries, each1024**, plus Decision-1 disabled,
  placeholder=true and capabilities=[routing-only]. The active set exactly
  equals the [route manifest](../gateway/catalog/project-routes.json).
- Customer `GET /api/model-garden`:200, the same ten enabled chat rows,
  backend_model equal to deployment alias, cap1024, capabilities=[chat].
  Decision-1 is disabled, coming_soon=true and routing-only.
- Admin `GET /api/admin/model-garden`:200, eighteen total rows; exactly those
  same ten are enabled chat rows. Old seed rows and auto are disabled.
  Disabled legacy caps such as auto16384 are not selectable chat allowance.
- Customer/admin router reads:200, enabled=false, default=gpt-5.6-luna,
  candidate set exactly the ten aliases. No auto chat choice exists.
- Source [accepted inventory](../gateway/catalog/foundry-inventory-20261026.json)
  has verified_at2026-10-26T12:44:49.521995+00:00, eleven deployments and ten
  gateway_validated chat route bindings, each1024 and expires_at=null. The
  focused test verifies manifest equality, provider token-field mappings and
  non-chat Decision-1. Source timestamp was not modified during verification.

**Release boundary:** current running `GET /api/model-deployments` returns404
through both customer and admin origins. The checked source defines this route,
an explicit audited sync operation and newer deployment-status UI. Therefore
this verification does **not** attest deployment of that source, runtime loading
of the accepted-inventory artifact, or execution of its newer sync operation.
The successful live metadata reconciliation is proven by readback; its prior
write/audit provenance was not recovered in this continuation. No sync was
blindly replayed. The live API behavior, not local source assumptions, determines
the runtime result.

## Decision-1 and remaining limitations

Decision-1 is routing-only metadata, **not a usable chat model and not verified
automatic routing inference**. The current catalog/admin UI still uses older
“Microsoft Decision-1 (model=auto) route simulator” wording. The newer
deployment-role/status UI is not attested deployed. Existing model cards and
admin rows are synchronized, but this wording/status presentation remains a
separate immutable application release task. Do not describe the simulator as
real Decision-1 execution. Pricing accuracy and monetary-ledger integration are
not verified; existing source changes are not proof that unknown-price wording
is deployed either.

## Security readback and bounded negative checks

Fresh ARM policy hash:
2d7899faa4b8c6494f76222913f64a1bcf290d95befc6815dc10d2cc93f48c05.
Protected global/legacy policy hashes matched the existing applied baseline both
before and after direct tests. The existing policy still has no expiry gate,
one backend forward, no retry policy, three safety checks and mandatory
fail-closed PII. TPM2048, Daily token quota10000, configured RPM60 and calls1000
per86400s remain the authorized POC controls. No counter keys or epochs changed.
Per-model token limits are not a ten-model aggregate budget or financial ledger.

At13:10:23–13:10:25: missing/invalid keys401; Decision-1 chat400; unknown
model400; cap1025 rejected400; customer/admin preflights200 with exact respective
allow-origin; untrusted preflight200 **without allow-origin** (browser CORS denial,
not an HTTP403 claim). Allowed-origin errors retained CORS. Local sanitized
[negative proof](../.deployment/project-models-current-negative.json) is retained.

Strict RPM/TPM and daily exhaustion were deliberately not driven to their limits.
Full adversarial live safety/PII acceptance was not performed. Structural policy
checks and passing unit/contract tests are not mislabeled as those live tests.

## Tests completed in this continuation

- 159 Python tests passed: persistent/model/demo/live guards, Foundry inventory
  and model-token suites.
- 104 additional Python tests passed: dev catalog, Turnstile, APIM project route,
  gateway policy and CORS contracts. Total **263 passed**, one existing Starlette
  deprecation warning per run.
- Terraform isolated project-route validate and recursive fmt-check passed;
  **11 mock tests passed, zero failed**. Existing development-provider override
  warning remains. No plan was applied.
- All three TypeScript workspace checks passed using the installed TypeScript
  JavaScript entrypoint. The npm command-shim route was blocked by Windows group
  policy; no machine policy was changed.
- Vitest was attempted separately but blocked **before collection** by native
  esbuild `spawn UNKNOWN`. No frontend unit-test execution pass is claimed.
- Editor diagnostics for inspected playground/sync/local verification files had
  no errors. Existing unrelated source/worktree changes were preserved.
- Saved public proof was checked offline against all ten fresh direct results,
  response identities, completion-token counts and manifest membership. The
  repository-wide whitespace check still reports an existing extra EOF blank
  line in [the unrelated root Terraform test](../infra/terraform/tests/disabled.tftest.hcl#L781);
  it was not modified as part of this verification.

Only verification artifacts, this report, current-status corrections and local
verification tasks/scripts were added here. There was no application code fix,
image rebuild, rollout, credential rotation, model provisioning or quota reset.