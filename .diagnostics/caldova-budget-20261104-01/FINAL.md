# Caldova November usage — final read-only diagnosis

**2026-11-04 · Diagnosis complete; production repair NOT performed or approved.**

## Verified result

The user-provided real CSV contains **201 unique completion rows**, of which **112** are in November UTC. The November sum is exactly **USD 0.043116564284** from **89 estimated** rows; **23 are unestimated**. This matches the retained authenticated Caldova monthly response, not a synthetic fixture.

All CSV rows use subscription `e9f2abb0-930b-598a-b210-0ab0b279127f`. The authenticated organization-scoped usage/budget receipts and pricing revision link this evidence to Caldova organization `00b30bd3-bf91-470d-b336-a192be32996e`. This is sufficient for the scoped telemetry join, but is not an independent current SQL inventory of every organization subscription.

- CSV SHA-256: `fd2e88467d514ecf8ea537cc1069c7575430738c1022303accc2373ba58f5bd2`.
- Pricing revision: `external:default:v1+org:00b30bd3-bf91-470d-b336-a192be32996e:v3`.
- November interval: `[2026-11-01T00:00:00Z, 2026-12-01T00:00:00Z)`.
- Retained telemetry cutoff: `2026-11-04T08:15:01.032739+00:00`.
- Retained budget response: `2026-11-04T08:19:39.622396Z`.
- Separate observations, not a repeatable-read database snapshot; all 112 row identities/statuses/times nevertheless agree.

## Why 23 are unestimated

**Every one of the 23 has `backend_attribution_missing`, with blank provider and region.**

| Status | Count | Observed evidence | Safe conclusion |
|---|---:|---|---|
| HTTP 400 | 11 | Empty model; no usage payload in retained projection; blank backend; no nonempty LLM request ID observed | Likely gateway rejects; exact stage and absence of billable activity not established |
| HTTP 403 | 7 | Same missing attribution/usage/backend pattern | Likely access/policy rejection; do not infer zero charge merely from status |
| HTTP 503 | 1 | Fast-model usage, input 294/output 0, Anthropic backend ID, one nonempty LLM request ID | Backend attempt observed; exclude from four-success repair; supplier charge/retry outcome unresolved |
| HTTP 200 | 4 | Fast-model usage and deployment, measured tokens/cache, one reported attempt | Four candidates for evidence-backed attribution repair only |

The 89 already estimated rows all retain **`price_missing`**, but the external estimate succeeds: **48 measured-cache-detail** and **41 standard-input approximations**. Thus `price_missing` is **not the cause of these 23 omissions**. The ingestion completeness label and independently calculated external customer estimate are different concepts. No error was assigned a fabricated zero cost; unknown cache detail remains unknown.

## Exact correlation and four successful requests

The offline audit verified **all 112** completion rows, including **all 23** unestimated records, using the ingestion key:

`SHA256(lower(resource_id) + ':' + correlation_id)`.

Subscription, status, and occurrence time agree. Telemetry has seven fractional-second digits; the CSV has six. Comparison truncates telemetry to microseconds and normalizes UTC suffixes, without rounding or JavaScript millisecond timestamps. Time is a cross-check, not an input to the request hash. Source: [ingestion.py](../../services/control-plane/src/aiflux/ingestion.py#L40-L41).

| UTC occurrence | Usage ID | Correlation ID | Input | Output |
|---|---|---|---:|---:|
| 2026-11-03 08:03:51.780837 | `6bbd09fc62759e944f1f593798d244384ddbd8f54f0f3d636fcf6751c6a62f04` | `834f9642-725d-41d8-b856-367b3fdd5cae` | 18 | 13 |
| 2026-11-01 22:57:26.496156 | `98a041b4764a12a7210083dcfe6143c7e918e2585faa63a82f7402352c67ca8c` | `b3bb2f56-0202-48e1-abc2-843160c7af31` | 569 | 233 |
| 2026-11-01 22:57:10.802936 | `2f8e983a53efdaa68985f84d795bf407d02461f5c3a44e4c4c480e3e3c863192` | `db6b58c8-7c6b-46e7-b6b9-86946df5a138` | 440 | 285 |
| 2026-11-01 22:57:01.293701 | `265e085b5c5804933fc69f0829447bd59d53cf49d177b5a6e3fe4a0779571be4` | `516900c4-9e4e-42b5-8a9f-d925fe982fc9` | 297 | 320 |
| **Total** | | | **1,324** | **851** |

For all four, retained `finops-v1` usage agrees with CSV input/output and measured cache-read/write counts **0/0**. Each has one usage trace, `attempts=[1]`, one observed nonempty LLM request ID, backend ID `aiflux-project-foundry-eight-anthropic`, usage alias/deployment **`claude-opus-5-5-fast`**, and LLM model label `claude-opus-5-5`.

**Historical routing is partially recovered, not fully proved.** The backend ID and fast deployment are historical request evidence. Their gateway region **Southeast Asia is not backend region**. The retained metadata lacks the endpoint/deployment-region mapping effective at each occurrence. A current catalog or candidate route is not sufficient to fill historical provider/region automatically. The ordinary LLM model label does not justify substituting ordinary Opus rates.

The retained query counts distinct nonempty LLM `RequestId` values, capped at three. Zero means no such ID was observed in this projection, not a supplier-confirmed zero invoice. One does not prove complete billable-stage coverage.

## Fast-model rates and conservative before/after

The authenticated customer catalog observation specifically for **`claude-opus-5-5-fast`** shows Anthropic/eastus, model version 2, GlobalStandard, displayed effective date 2026-10-27, and external USD/million rates **input 8, output 40, cache-read 0.4, cache-write 10**. These are administrator-configured external customer estimates, not supplier tariffs.

**Missing proof:** the full default/organization external revision event timeline, its `set`/`unknown`/`inherit` resolution and half-open validity periods at all four request times, plus historical backend-region attribution. A displayed date and revision identifier do not expose that timeline. No ordinary-Opus rate or supplier rate was substituted.

| Measure | Verified before | Conditional after all four proved eligible |
|---|---:|---:|
| Completion count | 112 | 112 |
| Estimated | 89 | 93 |
| Unestimated | 23 | 19 |
| Measured-cache-detail estimates | 48 | 52 |
| Standard-input approximations | 41 | 41 |
| Estimated USD | 0.043116564284 | **Not validated** |
| `estimate_complete` | false | false |
| Remaining USD | unknown/null | unknown/null |
| Budget status | unknown | unknown |

**Illustrative arithmetic only:** if the observed **fast-model** rates are proved effective for all four, `(1324 × 8 + 851 × 40) / 1,000,000 = USD 0.044632000000`; the corresponding total would be **USD 0.087748564284**. This is **not an approved or historically validated delta**. The machine report deliberately leaves validated delta and validated after-total null. A successful preview may differ if effective historical rates differ.

## Scoring telemetry: actual scope and counts

Retained November telemetry for the same APIM resource and subscription contains **20 unique `decision-overhead-v1` scoring invocations**, **76,389 input tokens**, **20 output tokens**, and HTTP-200 parents. All 20 parent correlations join the November completion CSV. These are **additional stages of those requests**, not 20 additional completion rows.

The separate customer scoring GET returned **26 rows across its 30-day window**; its November subset agrees with the 20-invocation metadata and reports **USD 0.003208338**, basis `measured_scoring_input_tokens`. That amount is a separate observed telemetry estimate. It is **not added** to the monthly figure here: no cross-store SQL absence/disjointness or complete invocation/retry coverage proof was obtained. It is not output-token pricing or a recovered invoice.

## Why the budget still cannot become complete

The retained production image inheritance/hash audit confirms the monthly-budget source was inherited without an overlay:

- Retained live API digest: `sha256:3f8d6e0d3eb833e9a76a8a411a178b2bf56f5703d4c68dcd5f7e8eb448c2b73c`.
- Parent digest: `sha256:440c63b274851a14e2c32416443a80df1e4c98202040b383250f1058bdc0168a`.
- Monthly source SHA-256: `9ea8dd7d13d4c93030634325c02daf79fe2ccc1e6871b35a9ecf03bbe466ec51`.
- This verifies retained build/source provenance, not a fresh runtime extraction or executed SQL preview.

The [monthly completeness guard](../../services/control-plane/src/aiflux/monthly_budgets.py#L93-L97) requires zero unestimated rows, zero approximations, available external pricing, **and `completion_count == 0`**. Here `completion_count` is **112**, not a count of rows missing prices. Even hypothetical repair of every omission would not defeat this billable-stage coverage guard; the four-row scenario also retains 19 errors and 41 approximations.

The [external pricing context](../../services/control-plane/src/aiflux/external_pricing.py#L120-L142) resolves historical events into periods at usage occurrence. The monthly calculation uses those expressions rather than stored `UsageRecord.cost`; setting a stored cost alone would not repair the customer estimate. No rate-history rewrite or completeness-label override is proposed as a shortcut.

## Disposition and durable evidence

**Feasibility:** a narrowly scoped four-record attribution correction is conditionally plausible. It is **blocked pending historical attribution and effective external-rate proof**, followed by a no-write preview and separate explicit write approval. The remaining 19 errors stay unresolved; trace-stage/provider evidence is needed to distinguish rejected requests from billable failed attempts. Do not force statuses to 200, replace unknown usage with zero, or hide failed records.

No additional cloud reads were necessary to establish the diagnosis and its evidence boundaries. No query intent was replayed. No credentials were extracted, no Python executed, no paid inference invoked, and no production data, pricing, configuration, build, runner, or deployment was changed. Only local diagnostic audit/report files were added.

- [Machine-readable final](FINAL.json)
- [Four-row one-off proposal and before/after gates](ONEOFF-PROPOSAL.md)
- [Offline CSV/correlation audit](final08.cjs)
- [Retained source provenance audit](audit07.cjs)
- [Authenticated customer observations](browser06.json)
- [Completion metadata](demo-completion-metadata05-result.json) and [original query](demo-completion-metadata05-body.json)
- [Scoring metadata](demo-scoring-metadata05-result.json) and [original query](demo-scoring-metadata05-body.json)
- [Telemetry scope](telemetry05-scope.json)

This final report supersedes earlier synthetic-fixture/October-only interpretations for the real November 89/23 case.