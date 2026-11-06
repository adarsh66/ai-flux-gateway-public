# One-off four-record correction proposal — NOT EXECUTED

**Disposition: blocked pending proof. No SQL, runner, ingestion replay, pricing edit, or production mutation is authorized by this proposal.**

## Scope and immutable allowlist

Organization `00b30bd3-bf91-470d-b336-a192be32996e`, subscription `e9f2abb0-930b-598a-b210-0ab0b279127f`, November UTC. Exactly four HTTP-200 `claude-opus-5-5-fast` completion IDs:

1. `6bbd09fc62759e944f1f593798d244384ddbd8f54f0f3d636fcf6751c6a62f04` — input/output 18/13.
2. `98a041b4764a12a7210083dcfe6143c7e918e2585faa63a82f7402352c67ca8c` — 569/233.
3. `2f8e983a53efdaa68985f84d795bf407d02461f5c3a44e4c4c480e3e3c863192` — 440/285.
4. `265e085b5c5804933fc69f0829447bd59d53cf49d177b5a6e3fe4a0779571be4` — 297/320.

All currently have blank provider/region and `backend_attribution_missing`; measured cache counters are 0/0. Keep IDs, ownership, occurrence, status, measured tokens/cache, and original evidence unchanged. Correlation IDs and timestamps are in [FINAL.json](FINAL.json). All 19 errors and all other usage records are outside the allowlist.

## Required proof before any write request

1. **Historical backend mapping per request:** verify backend `aiflux-project-foundry-eight-anthropic`, fast deployment identity, endpoint/account/model version/SKU, and provider/backend region from timestamp-appropriate retained deployment/policy/catalog or request metadata. Do not copy APIM gateway region or use current catalog as sole historical evidence. Preserve provenance for each proposed attribute.
2. **True effective external prices:** obtain existing default and Caldova external revision entries with owner/version/ordinal, operation, `valid_from`, rates, and cutoff. Resolve `set`/`unknown`/`inherit` exactly as the production external context does at each occurrence, including periods/applicability and input/cache normalization. Confirm the specific fast-model scope, not ordinary Opus, internal enforcement prices, or public supplier prices by analogy. Freeze/hash the read snapshot used for preview. Do not insert or backdate rates to make the rows eligible.
3. **Attempt and eligibility proof:** retained metadata already shows one usage event, attempts `[1]`, matching fast deployment, measured token/cache detail, and one observed nonempty LLM request ID for each. Check any missing retry/conflict/late telemetry before accepting final eligibility; the capped metadata is not a full provider billing ledger.
4. **No-write exact-expression preview:** in an approved detached/local data copy, restore only proven attribution and derive legitimate completeness from the established ingestion/FinOps rules, preserving any independent blockers. Do not simply label rows `complete` or `price_missing` to force eligibility. Evaluate the exact customer external-pricing expressions with the frozen event history, per-row amounts and aggregate deltas. No application changes, internal tariff updates, or production reingestion.
5. **Explicit later approval:** submit full before images and proposed after images, evidence hashes, exact four-row optimistic preconditions, preview result and rollback scope for approval. Approval for this read-only diagnosis is not approval to mutate data.

If any prerequisite is unavailable or conflicts, stop and retain the original records. Partial proof does not authorize even one write. If only some rows become verifiably eligible, produce a new explicit subset proposal; do not claim the four-row 93/19 outcome.

## Expected before/after, conditional on all four eligible

| Measure | Before | Conditional after |
|---|---:|---:|
| Observed completions | 112 | 112 |
| Estimated | 89 | 93 |
| Unestimated | 23 | 19 |
| Measured-cache-detail estimates | 48 | 52 |
| Approximations | 41 | 41 |
| USD estimated | 0.043116564284 | Baseline plus **validated preview delta**, currently unknown |
| Complete / remaining / budget status | false / null / unknown | false / null / unknown |

Current observed **fast-model** external rates are input/output 8/40 USD per million; their effective history is **not proved**. At those rates only, illustrative row amounts are USD **0.000664**, **0.013872**, **0.014920**, **0.015176**; sum **0.044632**, hypothetical aggregate **0.087748564284**. These are arithmetic illustrations, not accepted correction values. Do not use them as stored costs or invoice values.

## Future execution safeguards, only if separately approved

- Existing approved access only; no new runner, firewall, deployment, replay or unrelated configuration change.
- Use one approved atomic, optimistic-concurrency operation scoped to the four IDs and ownership; require exact expected before-state and affected count. Any mismatch rolls back/aborts, never broadens the predicate.
- Store immutable before/after/provenance evidence; derive completeness honestly, do not overwrite measured usage or statuses. Direct stored-cost edits alone are ineffective for the external monthly estimate.
- Leave external pricing revision/configuration, subscriptions, allocation, all other organizations, 19 errors, and 41 approximate rows unchanged.
- Verify through the same snapshot/expression that only eligible-row classification and corresponding external estimate change. Full expected result is 93/19, not 112/0; `completion_count=112` still prevents completeness.
- Preserve preimages for a separately approved compensating restoration of only corrected attributes. No rollback changes to pricing history or unrelated rows. No executable mutation script is supplied here.

## Remaining 19 errors and scoring

Keep 11 HTTP-400 and 7 HTTP-403 rows unresolved until policy/error-stage and dispatch evidence establishes whether any billable stage ran. Missing request IDs/usage traces do not establish nonbillability. The single HTTP-503 fast request has 294 input tokens, zero output and backend-attempt evidence: determine provider metering/retry/error semantics, not an invented zero or status rewrite.

The 20 observed November scoring invocations (76,389 input/20 output tokens) are separate stages sharing completion correlations. Do not insert duplicate completion rows or add the separate scoring estimate to monthly spend without cross-store coverage/disjointness proof. This proposal does not change the monthly safety guard or make remaining budget known.