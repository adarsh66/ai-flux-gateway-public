# Development product subscription access — live acceptance

## Policy rollout already complete; never replay

The exact saved plan `42bf402fb3456e6ea1c0e84c6f8a8b46f44f4fab726dd4ab930fed6336d1d292` was applied once at **2026-10-27 10:44:27.747661 UTC**, then independently verified at **10:47:40.848940 UTC**. See [policy-only evidence](../gateway/validation/product-subscription-access-20261027.json).

Only the original subscriber-ID predicate was removed. Authentication, nonnull subscription/product, exact `aiflux` product, all 11 models, safety, quotas and counter identities remain protected. The new source opt-in is constrained to the authorized persistent POC profile. Existing trusted admin creation/owned Reconcile already activates the product-scoped APIM subscription; no additional per-customer policy edit or Azure approval is required. No new subscription was created for acceptance.

## Actual customer-session acceptance

An existing customer tab identified itself as **Contoso**, and its selected subscription was the existing `d9768b6a-415c-5b2c-9c4e-fccaf92db250`. Acceptance used this customer UI, not administrator impersonation. The UI automatically revealed its own primary subscription key once and retained it only in React/browser memory. No administrator reveal was needed. No password, authentication storage, bearer token, provider secret or model key was extracted. The displayed organization proves customer scope; a fresh John password login was **not** performed or claimed.

Gateway: `https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1`.

| Actual operation | UTC | HTTP | Measured input / output / total | Result |
| --- | --- | --- | --- | --- |
| Contoso GET /models | 10:51:25.832 | 200 | Not applicable | Exactly 11 expected model IDs, including GLM |
| No-key GET /models | 10:51:25.884 | 401 | Not applicable | Anonymous access denied |
| Contoso POST /chat/completions, `gpt-5.6-luna` | 10:51:29.140 | 200 | 9 / 5 / 14 | Nonempty `Hello!`, finish reason `stop` |
| Contoso POST /chat/completions, `glm-5.3` | 10:51:47.012 | 200 | 15 / 367 / 382 | Nonempty greeting, finish reason `stop` |
| Original Caldova GET /models | 10:52:54.030 | 200 | Not applicable | Same 11 model IDs after policy change |

Both inference calls used only the benign prompt “Say hello.” with `max_completion_tokens=1024`, no streaming and no retries. Conversation was cleared between models. Total new measured consumption was **24 input + 372 output = 396 tokens**, over exactly two Contoso inference calls. There was no Caldova inference call. Caldova used its existing authenticated customer UI and one own-key reveal, entirely in browser memory, solely for GET /models.

All 11 expected IDs: `DeepSeek-V4-Flash`, `DeepSeek-V4-Pro`, `Kimi-K2.7-Code`, `gpt-4o`, `gpt-5.4-mini`, `gpt-5.6-luna`, `gpt-6.1-sol`, `grok-4-1-fast-reasoning`, `grok-4-20-reasoning`, `grok-4.3`, `glm-5.3`.

The sanitized browser observer returned only status, model IDs, token metadata, finish reason and bounded text from the test's own greeting. Keys and request headers never left browser memory or entered evidence files. Customer key reads during this acceptance total two; privileged administrator key reads total zero. The earlier policy-only evidence's `key_reads=0` remains correct for that earlier operation and is not rewritten.

## FinOps scheduled attribution checkpoint

At **10:53:24 UTC**, the authenticated Contoso usage and model-token APIs returned HTTP 200 and health `healthy`: last query success **10:50:00.284907 UTC**, watermark **10:45:00.284907 UTC**, scoped last row ingestion **10:50:01.976853 UTC**. These precede the new calls and therefore do **not** prove their ingestion. Existing Contoso history had three failed requests and zero measured tokens; it is not misrepresented as new successful traffic.

The administrator Showback organization selector was explicitly set to **Contoso**, separately from the customer session. A later natural scheduled pass and refreshed scoped aggregate are required to complete the new-call attribution check. No manual invocation, ingestion configuration change, cursor reset, replay, backfill, runner, logging change or repair is authorized or performed for acceptance. Billing remains unknown unless recorded pricing actually exists. The existing **06:06:02.045288 UTC** forward cutoff and historical deferred records remain unchanged.

At **10:55:59 UTC**, both customer Contoso and administrator Contoso-filtered usage APIs independently returned matching aggregates: four requests, three failed, **7 input / 12 output / 19 total tokens**; HTTP 200, health `healthy`, natural scheduled success **10:55:00.340018 UTC**, watermark **10:50:00.340018 UTC**, scoped row ingestion **10:55:01.424885 UTC**. The visible per-model chart included `gpt-5.6-luna`. This proves a subsequent scheduled pass and matching organization scope, but the 19-token record is **not** either new acceptance call (14 and 382 tokens). A separate narrow window **10:51:20–10:52:00 UTC**, restricted to the Contoso subscription in both sessions, is used for final attribution so unrelated traffic cannot be mistaken for these calls. A single browser-only refresh is scheduled for 11:00:15 UTC; it does not invoke or change the ingestion Function.

## Preserved controls and retained verification

- 60 requests/minute and 2,048 tokens/minute per subscription/model; 10,000 tokens/day per subscription/model; 1,000 calls/86,400 seconds per subscription; maximum completion 1,024; existing no-expiry POC profile.
- No quota reset, key rotation, suspension, product flag change, policy edit, application deployment, infrastructure mutation, role/network change or provider credential read during this acceptance.
- Retained verified results: **125** focused policy/guard tests, **5** APIM lifecycle tests and **23** Terraform mock cases. They were not rerun or relabeled as fresh execution here. Wrong-product/suspended-subscription negatives remain automated-test coverage only; no live subscription was interrupted to test them.
- Earlier independent policy readback verified all four image pins, protected settings, enabled timer, Always On and cutoff. This report does not pretend browser inference independently re-attests every ARM configuration field.
- The existing “not managed”/versioned-gateway notice is legacy UI wording, not evidence that the now-tested product subscription is blocked. No portal rebuild was performed to change that notice.

See [sanitized live acceptance evidence](../gateway/validation/product-subscription-live-acceptance-20261027.json) for exact operation scope and the final FinOps checkpoint.