# Sourced display pricing — 2026-10-27

## Scope and semantics

Display-only read-time estimates for already-stored and future measured usage
after the unchanged POC cutoff 2026-10-27T06:06:02.045288Z. No schema migration,
price-table import, usage-record rewrite, ledger/budget adjustment or ingestion
replay. Recorded financial cost and financial completeness remain separate.
Unknown tokens, failed requests, unsafe attribution and unsupported scopes stay
unestimated rather than becoming zero. Missing cache details use an explicitly
disclosed measured-input standard-rate approximation, not invented cache counts.

GLM contributes to the same usage totals as every other model. The intended
catalog contract marks only its rate TBC and exposes publisher source and the
explicit planning FX assumption. **Current checkpoint: the 13:22 UTC evidence-renewal
API release is applied; actual browser acceptance at 13:32–13:36 UTC passes all
11 catalog price cards/source links, GLM TBC, and same-window admin/customer
reconciliation.** See the latest checkpoint below; earlier failures remain history.
Two Grok reasoning variants use published family proxies.
These are list-price estimates, not actual negotiated charges or invoices.

## Rate provenance

All prices below are USD per million tokens, checked 2026-10-27. Live ARM
SKU/version matching is a pre-apply validation gate, not inferred from region.
The immutable manifest is
[rates-20261027.json](../services/control-plane/src/aiflux/pricing/rates-20261027.json).

| Alias | Input | Output | Cached input | Basis |
|---|---:|---:|---:|---|
| gpt-5.6-luna | 0.20 | 1.20 | 0.02 | Azure Global Standard short context |
| gpt-6.1-sol | 2 | 10 | 0.10 | Azure Global Standard short context |
| gpt-5.4-mini | 0.75 | 4.50 | 0.08 | Azure Global Standard; published cache rounding |
| gpt-4o | 2.50 | 10 | 1.25 | Azure Global Standard 2024-11-20 |
| DeepSeek-V4-Flash | 0.19 | 0.51 | 0.028 | Azure Global, not Flash 0731 |
| DeepSeek-V4-Pro | 1.74 | 3.48 | 0.145 | Azure Global |
| Kimi-K2.7-Code | 0.95 | 4 | 0.19 | Azure published exact model |
| grok-4.3 | 1.25 | 2.50 | Not published | Azure Global |
| grok-4-20-reasoning | 1.25 | 2.50 | Not published | Azure Grok-4.2 family proxy; exact reasoning tariff unverified |
| grok-4-1-fast-reasoning | 0.20 | 0.50 | Not published | Azure 4.1 Fast family proxy; exact reasoning tariff unverified |
| glm-5.3 | 1.14285714 | 4 | 0.28571429 | TBC: Zhipu publisher CNY8/28/2 divided by assumed 7 CNY/USD |

Luna/Sol cache writes are respectively USD0.25/2.50 per million; manifest limits
their short-context estimator to at most 128000 measured input tokens. GLM's FX
is an explicit planning assumption, **not a fetched exchange quote**, and the
publisher price is **not the ModelArts contract tariff**.

Public tables independently retrieved during this continuation:
- [Azure OpenAI](https://azure.microsoft.com/en-us/pricing/details/cognitive-services/openai-service/)
- [Azure DeepSeek](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/deepseek/)
- [Azure Kimi](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/kimi/)
- [Azure Grok](https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/grok/)
- [Zhipu GLM publisher](https://bigmodel.cn/pricing)

## Actual validation and rollout checkpoints

Backend and rollout guard regression report: 117 passed, zero failures/errors;
one existing Starlette/AnyIO deprecation warning.
[Backend JUnit](../gateway/validation/display-pricing-backend-tests-20261027.xml).

Native Linux ACR validation cm20: all workspace typechecks, 107 tests across13
files, and both production portal builds passed. Initial cm1y failed exactly two
stale disclosure assertions; one assertion update fixed both parameterizations.
Failed evidence and both build-intent markers retained; no failed image published.

Built artifacts: admin cm21, customer cm22, API cm23. These exact three images
were subsequently applied; see the independent release proof below. No ingestion build.
Existing npm audit warning: 1 moderate,1 high,2 critical vulnerabilities; pricing
did not alter dependencies, and validation is not a clean vulnerability-scan claim.

Pre-release authenticated existing-session usage evidence:
[pricing-before-acceptance-20261027.json](../gateway/validation/pricing-before-acceptance-20261027.json).
Contoso7 requests/506 measured tokens; Caldova21 requests/2826 measured tokens;
both recorded costs unknown. Scheduled ingestion health reported healthy with
last query success2026-10-27T11:40:00.255336Z. No inference added for acceptance.

## Initial applied release and historical live acceptance

The approved saved plan was already applied at **2026-10-27 12:19:09 UTC**.
Plan SHA-256: `3bb86f17090387efcb6bc65dec8eea2727d0677609f694057933cddcc6b7e8a4`.
Independent verification at **12:21:58 UTC** confirms
`protected_equal_except_three_images: true` and `ingester_unchanged: true`:
[release proof](../gateway/validation/pricing-runtime-release-20261027.json).
The immutable image digests are:

- API: `04ba655c24a87d30f3a47dbf091d2df03f52b2172f8d80b00f9eada7273eeb44`.
- Admin: `8950baf1fa8c5e8b0762c3b1069251706fe043dbca9c060b31c77092ba9f6ca0`.
- Customer: `072fe85e23168d20081894357ac87aa036e14363eb031e796e68686f4d357594`.

[Activation readback](../gateway/validation/pricing-activation-readback-20261027.json)
at 12:26:40 UTC reports all three sites Running, instances READY and configured
images matching. Container-detail responses were non-JSON and API/customer log
reads returned 504; those reads alone do not prove the running image digest.
Actual authenticated API responses and reloaded portal rendering were therefore
checked separately, without another build, apply, restart or configuration write.

**Final result: applied, customer usage acceptance passed; overall acceptance
is blocked by the live catalog and the existing admin authentication session.**
[Sanitized live evidence](../gateway/validation/display-pricing-live-acceptance-20261027.json).

### Authenticated customer usage — 12:36 UTC

Existing customer sessions were reloaded through the UI. Safe API response
capture was installed before ordinary Refresh telemetry actions. For count
comparison, only the usage GET's start/end parameters were temporarily pinned
to the exact pre-release UTC windows; these browser routing overrides were
removed afterwards. Chart viewport labels remained at their ordinary UI window,
so this is not a claim that the charts were pinned to those same boundaries.
All subscriptions/all models, 30 days:

| Organization | Exact UTC window | Requests | Input / output / total tokens | API estimate USD | Rendered USD | Estimated / unestimated / approximated |
|---|---|---:|---|---:|---:|---|
| Contoso | Sep 27 11:42 to Oct 27 11:42 | 7 | 61 / 445 / 506 | 0.001787028571 | 0.00178703 | 4 / 3 / 2 |
| Caldova | Sep 27 11:45 to Oct 27 11:45 | 21 | 1087 / 1739 / 2826 | 0.007271089999 | 0.00727109 | 19 / 2 / 10 |

Both returned HTTP 200 and revision `poc-public-20261027-v1`. Counts match the
pre-release evidence exactly, including zero missing-token requests. Independent
integer arithmetic using captured successful input/output measurements and the
manifest rates reproduces both estimates exactly, rounding each eligible row
to 12 decimal places before summation. GLM contributes USD 0.001763428571 for
Contoso and USD 0.005795999999 for Caldova to their **normal totals**, not a
separate TBC total. Neither usage page showed TBC wording.

Recorded cost remains Unknown/null, separately displayed from estimated cost.
Contoso's three unattributed HTTP 403 rows remain unestimated. Caldova's HTTP 403
mini row (41 input/20 output) and status-missing Sol row (99 input/0 output)
remain unestimated; their measured tokens remain in token totals. Missing cache
detail is disclosed as standard-input approximation (2 and 10 requests), not
fabricated cache measurements. TTFT remains unavailable. No inference or usage
was generated for this acceptance.

Fresh API health is healthy: last query success **12:35:00.200654 UTC** and
watermark **12:30:00.200654 UTC**, advanced from the pre-release 11:40/11:35
checkpoints. Observed lag was 395–414 seconds, below the 900-second stale limit.
This verifies continued scheduled progress, not a new independent ARM timer
configuration read; preservation relies on the existing protected release proof.

### Genuine outstanding acceptance blockers

1. **Catalog rates/source links/GLM TBC fail live acceptance.** At 12:37:29 UTC,
	authenticated `GET /api/model-garden` returned HTTP 200 and all 11 current
	aliases, but **every `display_price` was null**. The reloaded catalog rendered
	Unknown — not free for all input/output prices, no source links and no TBC
	badge. The source explanation is an exact-scope mismatch: the catalog calls
	`catalog_price(row.id, row.vendor, row.region)` using persisted catalog regions
	southeastasia (nine rows), eastus2 (mini), or unknown (GLM), whereas the manifest
	scopes are eastus or ap-southeast-1. Usage rows have the correct scopes and
	their estimates work. See the [catalog projection](../services/control-plane/src/aiflux/turnstile_exchange.py#L408-L413)
	and [exact rate lookup](../services/control-plane/src/aiflux/display_pricing.py#L40-L50).
	Manifest provenance is present in source; it is **not exposed by this live
	catalog response**. No catalog/DB edits or follow-up deployment were attempted.
2. **Admin organization reconciliation blocked by authentication.** The existing
	admin page was reloaded and refreshed normally. At 12:36:59.839 UTC,
	`GET /api/admin/usage/models` returned HTTP 401, `Invalid access token`.
	Organization options remained All organizations only. Therefore same-org,
	same-UTC admin/customer equality is **not verified**. A valid admin UI sign-in
	is required; no auth storage, token/header extraction, passwords, keys or
	authentication bypass were used.

Tests were not rerun for documentation/evidence-only edits. Existing backend
evidence remains **117 passed** (earlier checkpoint: 115); existing native Linux
evidence remains 107 tests, typechecks and both portal builds passed. These
regressions do not override the live catalog failure or admin authentication gap.

## Final API-only correction checkpoint — 13:08–13:09 UTC

This checkpoint supersedes the initial release's current-status conclusions,
not its historical evidence. The correction was already applied and verified at
**12:57:38.532119 UTC**: [correction release proof](../gateway/validation/catalog-pricing-correction-release-20261027.json).
Its saved-plan SHA-256 is
`aacc34680e9c8b8f96e0e2eed89a51d4bcee3f68a5f7ff9715b932efda8f8a8c`;
the API image digest is
`5df0ba96cbf9f6d40a593345734c5427a5f24a5d2be2066901f3b9d48424f1f6`.
The proof reports `protected_equal_except_one_api_image: true` and
`all_four_appsettings_hashes_unchanged: true`; admin/customer/ingestion images
remain the full 8950/072f/d2bd digests recorded in that proof. No build, plan,
apply, restart, configuration change or inference was performed for this final
read-only acceptance. A later prepared evidence-renewal plan is **not** treated
as applied, and its intermediate image is not substituted for this release.

[Correction live acceptance](../gateway/validation/catalog-pricing-correction-live-acceptance-20261027.json)
records actual authenticated browser response captures, using ordinary
navigation/reload and existing customer sessions, without reading auth storage,
headers, tokens, keys or passwords. The existing usage-page sidebar provided
the catalog URL; hidden-tab link clicks timed out, so normal URL navigation and
reload were used instead. No request interception or window override was added.

**Customer usage passes after correction.** Both usage GETs returned HTTP 200
for the observed UTC window **2026-09-27 11:52 through 2026-10-27 11:52**,
30 days/all subscriptions/all models. These are the actual normal browser
request boundaries, not the earlier 11:42/11:45 comparison windows.

| Organization | Captured UTC | Requests | Input / output / total tokens | API estimate USD | Rendered USD | Estimated / unestimated / approximated |
|---|---|---:|---|---:|---:|---|
| Contoso | 13:08:43.309 | 7 | 61 / 445 / 506 | 0.001787028571 | 0.00178703 | 4 / 3 / 2 |
| Caldova | 13:08:50.602 | 21 | 1087 / 1739 / 2826 | 0.007271089999 | 0.00727109 | 19 / 2 / 10 |

Both totals still equal the independently calculated earlier values, despite
the different observed window boundaries; no extra inference was generated.
Revision remains `poc-public-20261027-v1`, recorded cost remains null/Unknown,
and neither usage page shows TBC wording. Health is healthy, with last query
success **13:05:00.839702 UTC**, watermark **13:00:00.839702 UTC**, and observed
lags 523/530 seconds below the 900-second threshold.

**Catalog acceptance does not pass.** Caldova's normal catalog reload at
**13:08:34.856 UTC** returned HTTP 503; Contoso's navigation at
**13:09:13.669 UTC** independently returned HTTP 503 with
“Verified Foundry deployment inventory is unavailable or expired”. The UI
renders this error, not eleven price cards. Therefore all-11 numeric rates,
source links and GLM's 1.14285714/4 TBC presentation are **not verified live**.
This is a new fail-closed inventory gate observation, not the old HTTP 200 with
eleven null display prices. It does not prove a running image digest or unique
backend version; image identity relies on the existing release proof.

The current [catalog projection](../services/control-plane/src/aiflux/turnstile_exchange.py#L394-L413)
uses [accepted-route pricing](../services/control-plane/src/aiflux/display_pricing.py#L54-L86),
not the old persisted-region lookup. The
[inventory loader](../services/control-plane/src/aiflux/foundry_inventory.py#L70-L109)
enforces freshness and scope before catalog rendering; this shared 503 message
alone does not identify which internal validation branch failed. The immutable
manifest still contains all 11 numeric rates, the five source URLs above, and
GLM's explicit TBC publisher/FX assumption. Source and regression evidence are
not a substitute for unavailable live cards.

**Admin remains blocked.** The only existing admin page offered by the browser
was showback. Its normal reload at **13:08:57.054 UTC** returned HTTP 401
`Invalid access token` from `/api/admin/usage/models`. No other valid existing
admin page/session was available in the browser's page listing. Same-org,
same-window admin/customer reconciliation remains unverified pending valid
admin UI sign-in; no authentication bypass was attempted.

Existing XML records were read, not rerun: correction suite **66 passed**,
evidence-renewal suite **121 passed**, each with zero failures/errors/skips.
These overlap and must not be summed as unique tests. Earlier backend **117**
and native Linux portal **107** passing checkpoints remain historical evidence.
Overall result: **correction applied; customer usage passed; catalog and admin
live acceptance blocked — not 100% complete.** This documentation-only pass
does not authorize or execute another deployment.

## Latest applied evidence-renewal release — actual browser acceptance 13:32–13:36 UTC

This checkpoint supersedes the earlier current-status conclusions. The
[release proof](../gateway/validation/catalog-pricing-evidence-release-20261027.json)
records actual application at **13:22:16.529476 UTC**, plan SHA-256
`22f98df2060057cc5527ad5f6fd80307f2a9256232d19447dec3d8f4d1ee8929`, API digest
`b47ba73081698e5cb29e50cbe6f415752703fdd8f1122015a53638c59fea7899`,
`protected_equal_except_one_api_image: true` and unchanged four app-settings
hashes. [Readiness](../gateway/validation/catalog-pricing-evidence-readiness-20261027.json)
at **13:23:47 UTC** reports Running/READY and that configured digest. Image
identity relies on release/readiness evidence, not inference from browser data.
No additional build, plan, apply, restart, cloud configuration write, inference,
usage replay, auth-storage/header/token/key inspection or auth bypass occurred
during this acceptance. Existing authenticated pages were ordinarily reloaded.

**Catalog passes live.** The usage sidebar supplied `/models` (not `/catalog`).
At **13:34:00.538 UTC**, the captured authenticated `/api/model-garden` response
was **HTTP 200**, with all 11 non-null display prices. Separate rendered-card
inspection at **13:32:30.470 UTC** verified all eleven numeric input/output
rates against the rate table above, each card's public pricing link and
Playground link, and GLM input **USD 1.14285714 · TBC**, output **USD 4 · TBC**,
cached input **USD 0.28571429**. Only GLM carried TBC. Grok cache rates remain
Unknown, not zero. The earlier 503 is resolved in this observation, not repeated
as a new failure. Links were inspected, not followed to generate inference.

Inventory validity and catalog routing configuration are separate: the
[inventory loader](../services/control-plane/src/aiflux/external_inventory.py#L76-L90)
still requires the verified Foundry inventory; the
[pricing projection](../services/control-plane/src/aiflux/turnstile_exchange.py#L394-L413)
prices accepted bindings. Readiness reports `AIFLUX_CATALOG_CONFIGURED=false`;
this was not blindly changed and does not invalidate the actual HTTP 200
pricing result. It is not a claim that routing configuration was enabled.

**Usage and admin reconciliation pass.** Normal UI period boundaries remained
**2026-09-27 11:52 through 2026-10-27 11:52 UTC**, 30 days/all models.
Existing customer sessions returned HTTP 200 (Caldova **13:34:42.156**, Contoso
**13:36:15.160 UTC**). Admin's existing session now also returned HTTP 200,
including organization options; the historical 401 is not current. Ordinary
Organization selections captured Caldova at **13:36:03.654** and Contoso at
**13:36:05.335 UTC**, both HTTP 200 for the same boundaries, with exact equality:

| Organization | Requests | Input / output / total tokens | Customer and admin estimate USD | Estimated / unestimated / approximated |
|---|---:|---|---:|---|
| Contoso | 7 | 61 / 445 / 506 | 0.001787028571 | 4 / 3 / 2 |
| Caldova | 21 | 1087 / 1739 / 2826 | 0.007271089999 | 19 / 2 / 10 |

Recorded cost remains null/Unknown, distinct from these numeric estimates.
No request interception or artificial time-window override was used. Latest
observed query success **13:35:00.235316 UTC**, watermark **13:30:00.235316 UTC**,
health healthy, lag **364–375 seconds** below 900 seconds, demonstrate continued
scheduled progress without additional inference or a timer write. The original
cutoff remains **2026-10-27T06:06:02.045288Z** per protected release evidence.

Existing [JUnit evidence](../gateway/validation/catalog-pricing-evidence-tests-20261027.xml)
confirms **121 passed, zero failures/errors/skips**, not rerun or summed with
overlapping suites. [Sanitized final acceptance](../gateway/validation/catalog-pricing-evidence-live-acceptance20261027.json)
records the current result. **Requested pricing/catalog and same-window
showback acceptance: passed.** Earlier 503/401 records remain historical only.