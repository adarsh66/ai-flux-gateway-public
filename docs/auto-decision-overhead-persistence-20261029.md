# Auto decision overhead — source-only trace-store persistence

## Scope and accounting

The production Auto resolver now emits one `aiflux` trace at severity
`information`, category `decision-overhead`, payload schema
`decision-overhead-v1`. It runs **after** the resolver result passes all existing
validation and the empty-result 503 guard, **before** selected-model limits,
provider request rewriting and backend dispatch. It does not emit a second
completion. A later provider error or limit rejection does not erase the decision
already made. Invalid/failed selection emits no overhead event in this change;
absence is not zero latency, zero tokens or a successful decision.

The payload is an explicit projection: `request_id` from `context.RequestId`,
`routing_profile`, `selected_model`, `config_version`, `latency_ms`, nested `usage`
with nullable `input_tokens` and `output_tokens`, and nullable `cost_usd`. Latency
is the existing measured interval from immediately before gateway-MI acquisition
through successful resolver validation, not provider latency or TTFT. Resolver
tokens are accepted only as nonnegative integers at most 2,147,483,647; absent or
invalid counters remain null. No decision price has been verified, so cost stays
null, never inferred from the selected provider's price. Fixed schema/UUID,
source-bound three profiles/six aliases/64-character config hash, latency at most
120,000 ms and bounded counters keep the compact payload below 2,048 UTF-8 bytes.
No prompts, messages, response bodies, probability maps, instructions, exceptions,
credentials, subscription keys, tokens or client-supplied correlation are copied.

Emission is entirely within
[gateway/policies/auto-resolve.xml.tftpl](../gateway/policies/auto-resolve.xml.tftpl),
which is composed only for Auto-enabled policy. The shared policy, original
completion metadata and `finops-v1` provider usage remain unchanged. Auto OFF
retains byte-identical rendered policy for all thirteen explicit routes. Original
safety, PII, daily call quota, selected-provider limits and no-fallback behavior
are preserved.

## Existing persisted trace store — no DDL or infrastructure additions

[infra/terraform/apim.tf](../infra/terraform/apim.tf) already declares the existing
`azureMonitor` logger and diagnostic with `verbosity = information`, fixed 100%
sampling, no client IP and zero request/response body capture. The existing
dedicated Log Analytics `GatewayLogs` destination supplies
`ApiManagementGatewayLogs.TraceRecords`. This change reuses that configured trace
store and its existing retention/access controls; it adds no resource, logger,
table, migration, SQL column or write to `UsageRecord`.

This is **source evidence**, not a fresh read of actual Azure configuration.
No cloud configuration read or write was needed or performed here. Successful
actual trace persistence still requires the deployed API to inherit the existing
logger/diagnostic at information verbosity and a runtime observation of the event.
Do not conflate App Insights request telemetry with this resource-specific Monitor
table. No new standalone Application Insights resource is needed. If an existing
App Insights diagnostic is also configured, it must independently admit
information traces; its presence/destination has not been freshly verified.

The dedicated query is
[services/control-plane/src/aiflux/queries/decision-overhead.kql](../services/control-plane/src/aiflux/queries/decision-overhead.kql).
It uses the same trusted formatter parameters as the existing usage query, scopes
time/resource/product/chat operation, deduplicates parent gateway rows by resource
and correlation, parses either object or JSON-string trace metadata, requires the
exact category/schema and gateway request ID, and rejects duplicate decision
events. It correlates one decision to the parent gateway completion/status by
resource ID plus `CorrelationId`. Its final projection contains only allowlisted
decision fields and parent metadata, not raw traces. A parent may have failed
after selection; `parent_status_code` remains visible. Query windows are based on
the parent log time; absence can also mean retention, delay or no valid decision.

Decision tokens/cost are explicitly separate from parent provider counters. The
query is not a second ingestion feed and never joins/sums native LLM subrequest
tokens. Existing ingestion, `usage.kql`, `UsageRecord`, watermarks and pricing are
unchanged. Existing package-data wildcard includes the new query automatically.
The API's SQL-backed usage responses do **not** gain overhead fields in this
change: persisted means retained/queryable in the existing trace store, not SQL.

## Validation and release boundary

New offline tests cover trace placement/cardinality, XML/C# source projection,
bounded schema shape, null semantics, all-thirteen-route Auto-OFF identity, query
parameter/correlation/deduplication contracts, diagnostic **source** settings and
synthetic local ingestion proving no second row/token/cost accounting. Terraform
console evaluates local render expressions only; these tests do not establish
APIM C# runtime compatibility or execute KQL against Azure Monitor.

No historical diagnostic package, manifest or bound script is edited or restamped.
The changed production resolver is a new source successor, not a claim that an old
frozen package validates current source. No diagnostic activation, Send, build,
replan, policy publication, settings change or deployment is authorized by this
change. Browser readiness remains a separate unresolved gate.

API publication receipt tooling is deferred: actual gateway-MI scoring/response
proof, exact deployed-policy readback, authorization evidence and independent
release review remain necessary. The existing receipt reader is unchanged; no
receipt is manufactured and `runtime_verified` is never self-set from offline
tests or diagnostics metadata. A future release must bind the exact new policy
hash/snapshot to real evidence before publishing a receipt to the API. No runtime
verification, browser acceptance or overall completion is claimed here.

## Actual offline results — 2026-10-29

- New trace/render/query/accounting tests plus existing FinOps ingestion tests:
	**46 passed**, zero failures/errors. Final receipt:
	[.deployment/decision-overhead-source-tests-final-20261029.xml](../.deployment/decision-overhead-source-tests-final-20261029.xml),
	SHA256 `b6350c1e2fbda2d73a1b8503113d8bf34431337354defa65fc8fb800acd9a905`.
	The earlier report retains one test-helper failure (an unrelated existing trace
	lacked category metadata); the helper was fixed rather than changing gateway behavior.
- Existing focused source validator: **94 passed, 29 deliberately deselected**,
	zero failures/errors, exit 0. Only `real_rendered_csharp` tests were deselected
	because they invoke a .NET build; no esbuild or .NET build was run. Actual result:
	[.deployment/gateway-direct-focused-20261029T134021720527Z/result.json](../.deployment/gateway-direct-focused-20261029T134021720527Z/result.json).
	[JUnit](../.deployment/gateway-direct-focused-20261029T134021720527Z/tests.xml)
	SHA256 `4eb9718ce573a65c6dd9b6aa47ce4e65a4a483faa40a83f966a8d921efd96408`.
	Both runs retain an existing Starlette/AnyIO deprecation warning.
- A before/after byte-hash comparison of 191 protected files (Python/MJS scripts,
	gateway catalog, inventory implementations, shared policy, Auto completion/error
	metadata, composition, diagnostics infrastructure, ingestion/model/usage query
	and API receipt reader) is identical. Aggregate SHA256:
	`c3aadc4e5c72e6c09d801d47b3dd825a7b10ea63f6cee6cc314665f4227e5436`.
- Read-only inspection confirms the retained diagnostic06 manifest actually binds
	the old resolver SHA256 `ceca391a70bc951bb3f4cab9ef575d8efbed7d394bd69bdd9fcba8890a2c7eff`.
	The new resolver is `504fd3a658d99a3323fb92a0602d4f03077634f92ef9d5104a178fd0fc91ab77`.
	The manifest remains `29ae11a25d3e65a7480d54db08117484561749eb29553309fbf81772b9e6f3e9`.
	Thus old source-freshness checks must reject this successor; **do not alter,
	restamp, refresh or activate that historical package**. No package check,
	preparation, activation or browser Send was invoked.