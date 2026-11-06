# Eight Foundry models — LIVE, scoped rollout complete

Final retained rollout report: **2026-10-30T19:57:20.094367Z**; integrity proof:
**2026-10-30T19:57:20.484028Z**. Final read-only UI inspection:
**2026-10-30T20:00:05.564Z**. These are actual machine UTC timestamps.
The `20261031` directory/document labels identify the user session, not a later
deployment or a restamped observation.

## Verified availability and pricing

All eight names below appear in the customer catalog and normal Playground
selector. The reloaded admin rate card renders **21 rows**, including all eight;
Anthropic/OpenAI additions say **Public list rate**, and Mistral says **Proxy
rate**. Customer cards show matching input/output rates and source/assumption
metadata. Prices are USD per million tokens, estimates only, not invoices.

| Exact public alias | Input / output rate | Original input / output tokens | Retained usage estimate USD |
|---|---:|---:|---:|
| `claude-sonnet-5-5` | 2 / 10 | 18 / 13 | 0.000166000000 |
| `claude-opus-5-5` | 4 / 20 | 18 / 13 | 0.000332000000 |
| `claude-opus-5-5-fast` | 8 / 40 | 18 / 13 | 0.000664000000 |
| `claude-haiku-5-5` | 0.10 / 0.50 | 18 / 13 | 0.000008300000 |
| `gpt-6.1-terra` | 1 / 5 | 12 / 5 | 0.000037000000 |
| `gpt-6-luna` | 0.10 / 0.50 | 12 / 7 | 0.000004700000 |
| `claude-opus-4-8` | 5 / 25 | 16 / 9 | 0.000305000000 |
| `Mistral-Large-3` | 0.50 / 1.50 | 9 / 7 | Unknown — missing cache detail |

Mistral's rate is explicitly a **publisher-family sourced proxy**, not a verified
Azure Large-3 deployed-version tariff. Its customer cached-input rate is Unknown;
missing cache measurements are not zero/free. Seven retained requests have
measured-cache-detail estimates; Mistral remains the one unestimated request.
Claude short-context/CCU and cache-write-TTL assumptions remain disclosed.

Configured membership is **old 13 + new 8 = 21 chat aliases**, with Decision-1
separate and disabled/routing-only (22 inventory entries). This is **not** a claim
that 21 models are customer-selectable. Existing operator flags were preserved:
customer catalog, model API and Playground expose **nine**, exactly the new eight
plus existing `glm-5.3`. All **21 pre-existing database garden rows** were preserved
in full; inserting eight yields 29 admin garden rows. Those database-row counts
are distinct from the 13 historical configured chat aliases.

Read-only inspection at 19:59:39–19:59:40Z confirmed all eight in both admin
Showback and customer Usage model filters, with charts loaded and no alerts.
These are data-driven usage options, not a hardcoded selectable-catalog count;
historical disabled models can still appear in usage. The 21-row rate card stayed
at version 2, unchanged; Save changes was disabled. No Save or Send was used.

## Inference and accounting provenance

[Original eight-call proof](../.deployment/foundry-eight-offline-promotion-20261031/all-eight-usage-proofs.json):
**exactly eight transport invocations, all HTTP 200, nonempty assistant text,
121 input + 80 output = 201 tokens**, no replay or remaining inference budget.
Original response/correlation IDs and hashes remain retained. Terra's raw model
field remains null; its identity is resolved by exact correlated dated LLM
metadata. Mistral's deployment-to-provider-model mapping is explicit, not generic
case folding. Fast-mode acceptance is exact policy/normalizer guard-based proof,
not latency inference or a retained direct native trace.

[Authenticated usage evidence](../.deployment/foundry-eight-catalogfix-20261031/apply-once-01/usage-verification.json)
records 16 filtered detail/CSV GETs, all HTTP 200: one stored request and one CSV
row per alias, with detail/summary/CSV estimates agreeing (**7 estimated,
1 unknown**). Original tokens, null recorded cost/currency, blank stored
provider/region and `backend_attribution_missing` completeness remain unchanged.
Read-time estimates do not repair or rewrite stored financial/attribution fields.
Admin/customer filter availability is verified; this report does not invent an
independent same-window admin/customer aggregate-equality measurement.

## Final immutable runtime and gateway

Registry: `pocidstokenexacr.azurecr.io`; all pins below are `sha256` digests.

| Component | ACR run | Repository | Final digest |
|---|---|---|---|
| API | `cm3x` | `aiflux-api` | `c098efb94afe3d6d56fd39f4f2a859f16f3846682dae161f89d483c5ddd275ac` |
| Admin | `cm3t` | `aiflux-admin` | `0d5bc4e60af8d003c786c0b511f4d4bb7a8926ae8883a4fbffe8aff0139b5ca5` |
| Customer | `cm3u` | `aiflux-customer` | `cb12513df262891762d6c59017ee8bc8aad3879ddc78b0eccfd318f1eec92e53` |
| Ingestion | `cm3v` | `aiflux-ingestion` | `d60816f38b399f3e9f925b4dacf998ca3df08e393f884406a91cbf113cc2798e` |

[Final protected readback](../.deployment/foundry-eight-catalogfix-20261031/apply-once-01/postapply-snapshot.json)
confirms these four pins. Final API-only corrective apply ran once, exit 0,
0 added / 1 changed / 0 destroyed, state **119 → 120**, lineage
`b05cbf70-2d31-0e6e-34b7-c97e8f617ed6`. Saved plan SHA-256:
`248c200c6904ce279cb5a64ac524e91d2e2e57df027ae8126ce1c31b0a77288a`.
Official validation completed through UpdateStatus. Never replay consumed plans.

The additive APIM release's two backend names remain
`aiflux-project-foundry-eight-anthropic` and
`aiflux-project-foundry-eight-mistral` (six backends total, not two total).
[Backend hashes](../.deployment/foundry-eight-catalogfix-20261031/apply-once-01/postapply-backend-hashes.json)
and active policy SHA-256
`c0638ec3a9c403402c565f8d8ae3e3c105a1a998eafbc80456b5841fe47b8ca6`
match before/after the corrective API apply. All four settings collections,
other three image pins, APIM 21-route configuration and protected security state
were unchanged. One previously approved chat-only sync returned HTTP 200 at
19:54:51.226Z; router remained disabled and its complete configuration unchanged.
This documentation pass did not repeat that mutation.

## Retained validation — separate runs, not an aggregate

| Evidence / scope | Result |
|---|---|
| [Offline identity/catalog promotion](../.deployment/foundry-eight-offline-validation-20261031/result.json) | 214 passed; 0 failures/errors/skips |
| [Corrected local catalog/pricing/sync regression](../.deployment/foundry-eight-catalogfix-20261031/focused-corrected.xml) | 245 passed; 0 failures/errors/skips |
| [Native Linux API build cm3x](../.deployment/foundry-eight-catalogfix-20261031/build-result.json) | Succeeded; 245 targeted tests retained |
| [Final corrective-apply local guards](../.deployment/foundry-eight-catalogfix-20261031/apply-once-01/offline-proof.json) | 3 passed |

These suites overlap; do not sum them into a unique-test total or claim a full
repository suite. The earlier misleadingly named local green receipt actually
contains one synthetic fixture failure; it is retained, not counted as green.
The corrected fixture and subsequent clean receipt are distinct. No tests were
run during this final documentation pass, including no Auto tests.

## Warnings and scope closure

- Dedicated readiness endpoint **not verified**: portal readiness returned 404
  (not proxied); direct browser request tooling failed before an HTTP result.
  Authenticated admin/customer identity and application data GETs returned 200;
  functional readiness is verified without claiming readiness-endpoint 200.
- Usage pages still display legacy “restated at current rates” subtitle wording.
  That text is not proof of financial repricing; unchanged stored fields and
  retained detail/summary/CSV evidence above are authoritative.
- [Final integrity](../.deployment/foundry-eight-catalogfix-20261031/apply-once-01/final-integrity.json)
  passed, binds the actual report/receipts and state 120 proof; the retained
  [worker inspection](../.deployment/foundry-eight-catalogfix-20261031/apply-once-01/final-workers.json)
  records zero competing workers at 19:57:20.089907Z. No fresh process or cloud
  absence claim is substituted for that timestamped local proof.
- Source contexts remain isolated; historical/frozen Auto modules, default
  manifests and their bound hashes were not edited/restamped by this pass.
  No full-working-tree rebuild, source change, cloud/DB mutation, inference,
  install, prepare, release or new test was performed here. Only this report,
  the top handoff addition and existing session memory were updated.
- **Auto/Decision-1 remains ON HOLD**: no preparation, release or tests. The ninth
  discovered `mistral-medium-3-5` remains excluded. Streaming/tools/multimodal
  support is not claimed. The approved eight-model rollout is complete; the
  stated warnings do not require another deployment, sync or inference call.

Primary completion evidence: [final report](../.deployment/foundry-eight-catalogfix-20261031/apply-once-01/final-report.json)
and [authenticated browser verification](../.deployment/foundry-eight-catalogfix-20261031/apply-once-01/browser-verification.json).