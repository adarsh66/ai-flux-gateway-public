# Configure the bounded exact-project gateway

## Current explicit persistent POC (supersedes historical expiry below)

On 2026-10-26 the user explicitly authorized **no expiry**, output**1024** and
TPM**2048**. This is applied on the existing /dev/llm/v1 API with all ten current
deployment routes preserved. RPM60, daily10000 tokens per subscription/model,
1000 calls/86400 seconds per subscription, retry0, threshold1, authentication,
product/subscriber/CORS, safety and PII remain unchanged. No counter names or
epoch were changed. This is **not production acceptance** or a dollar budget.

Use [the current report](persistent-poc-controls-20261026.md) and
[persistent-profile guard](../scripts/deployment/project_route_persistent.py).
The explicit `persistent_poc_authorized` input requires an empty expiry, not a
far-future timestamp. Original defaults and candidate/expiring-demo guards are
retained for historical contracts; do not replay their saved plans or use old
quota/model variable files to revert the persistent profile. All model-specific
request validation limits render from the same output input. Provider-native
constraints still apply;1024 is a gateway ceiling, not a claimed provider limit.
The existing customer portal reads the API metadata; Luna is synchronized1024.

## Historical expiring demo evidence

Source defaults alone never authorize activation. A separately user-authorized
expiring **RPM60 demo is now deployed** on the final route; strict rate testing
is explicitly deferred, not passed. TPM1000/daily10000/output32/threshold1 and
mandatory safety/PII remain. Current API and authenticated browser both return
HTTP200 with real assistant text after the user-authorized daily call allowance
increase to **1000 calls per 86400 seconds** at 2026-10-26T06:37:16Z. The same
counter key/epoch and fixed expiry are retained. Exact-origin CORS still covers
successes and failures. No fabricated safety/token-quota acceptance; see the
[current evidence](apim-route-repair-20261026.md).

## Where to edit values

The isolated module's [input variables](../infra/project-route/main.tf) are the
configuration source. Copy values from the non-auto-loaded
[example](../infra/project-route/conservative.example.tfvars.json) into the
operator's reviewed project-route variable file. Do not edit generated XML,
saved plans, the shared legacy policy, runtime settings, or acceptance evidence
to change these limits. Terraform input changes require a **new** render, saved
plan, independent scope guard and validation; an old plan does not pick them up.

| Input | Default | Meaning / validation |
| --- | --- | --- |
| `rpm_limit` | 1 | Positive integer valid POSTs per subscription/model/minute |
| `rate_limit_window_seconds` | 60 | Exactly 60, so RPM cannot silently become calls/hour; APIM's general maximum is 300 |
| `tpm_limit` | 1000 | Integer prompt + completion tokens/minute; at least the output cap |
| `daily_token_quota` | 10000 | Integer total tokens/day, at least TPM; fixed `Daily`, resets at UTC midnight |
| `daily_call_allowance` | 8 | Original conservative default; separately authorized live demo override is 1000. Only 8 or 1000 accepted; candidate always stays 8 |
| `completion_token_limit` | 32 | Integer 1–32; request and model-specific output bounds change together |
| `backend_retries` | 0 | Only zero accepted; exactly one forward, no retry policy |
| `safety_threshold` | 1 | `EightSeverityLevels`; all four categories, all three safety passes |
| `enabled` / `candidate_validation` / `acceptance_verified` | false / false / false | Configuration never supplies deployment or acceptance authorization |

The original candidate profile remains RPM1; the explicitly authorized final
demo profile is **exactly RPM60**, window60, TPM1000, daily10000 and the stable
**1000-valid-POST/86400-second** demo ceiling, with the unchanged fixed expiry
2026-10-27T05:41:01Z. The dedicated [quota runner](../scripts/deployment/project_route_quota.py)
uses the reviewed quota inputs and exact saved plan in the existing isolated
state, never the destructive original candidate/demo lifecycle. The old demo
inputs and original creation plan are retained as historical predecessor proof,
not the current quota configuration. Do not rerun them to overwrite this update.
Other valid
source inputs are not authorization to deploy them: the independent candidate
guard rejects changes to these controls, deferred rate increments and counter
identity, even if the saved plan matches the altered render. Output may only be
tightened within 1–32. Raising safety threshold requires separate policy review;
the enabled-route precondition still permits only the authorized threshold1.
The existing deployment remains gpt-5.6-luna/2026-07-09 on the exact
poc-ids-token-ex-foundry project; no automatic model substitution is introduced.

## What stays mandatory

Original input safety and prompt shield run **before** PII redaction; redacted
input is checked again; output is checked before release. Five bounded PII batches
retain fail-closed service/response validation. None is an optional switch here.
For APIM's supported `EightSeverityLevels`, severities are 0–7 and content with
severity **at or above** the threshold is blocked. Thus threshold1 permits only
severity0; threshold0 blocks benign severity0 too. Higher numbers are more
permissive, not safer. Outbound safety is explicitly in outbound; APIM ignores
`enforce-on-completions` there, so no unsupported attribute is needed.

Counters retain the existing `rpm:` / `tpm:` + subscription ID + model identity
and `project-validation:` (candidate) / `project-demo:` (live demo) + subscription ID. No timestamp, release ID, limit,
policy hash or candidate/final API name is added. Reapplying configuration must
not intentionally mint a new allowance or move the quota epoch. Do not delete
and recreate counters to make tests pass. This avoids source-induced resets;
it is **not** a guarantee of counter persistence across APIM platform restarts,
resource recreation, gateway changes or policy removal. APIM documents distributed
rate approximation and quota overshoot. A strict global spending reservation
requires a separate authoritative atomic ledger.

## What counts as acceptance

Real, attributable runtime tests must prove missing/invalid-key rejection,
unsupported request rejection, benign MI completion, prompt-shield rejection,
original/redacted/output filtering, PII redaction and unavailable/malformed PII
fail-closure, RPM429, TPM429 and daily-quota403. Use approved non-graphic synthetic
fixtures, scoped safe failure injection and low output caps; do not publish
prompts, responses, keys or traces. A benign200 only proves that one path ran,
not that negative controls work. Offline mocks/rendering and a checkbox never
set acceptance to true. Do not burn 10000 tokens just to exhaust the daily quota:
any separately reviewed lower-limit test must preserve stable counters and
rollback, and must not replace acceptance of the actual deployed configuration.

The runner now records UTC start/end, monotonic start, elapsed seconds and fixed
numeric remaining-counter headers. A second request outside the minute is
**inconclusive**, not a failure or pass. A429 caused by TPM is not RPM proof.
Even an attributed RPM429 is one observation, not a strict distributed maximum.
The two inference calls are bounded distinct probes, not automatic retries.
The RPM60 demo telemetry and error-response CORS were compiler-tested and
deployed. The former eight-call403 was observed in API/browser; the subsequent
calls-only increase was applied and both real API and rendered browser responses
were200. These two bounded hello calls used21tokens each (42total), output12each.
The direct call reported9979daily tokens remaining before the browser call;
that is an estimate at that time, not an exact current balance or reset proof.

GET models returns before POST counters. CORS is first and preflight is not an
inference request. Malformed/unsupported POSTs are rejected before the model
counter; valid POSTs rejected later by safety still consume request allowance.
The fixed response headers `x-aiflux-rpm-remaining`, `x-aiflux-rpm-limit`,
`x-aiflux-tpm-remaining`, `x-aiflux-daily-tokens-remaining` and `Retry-After` help
operators inspect behavior. Token remaining values are estimates. The runner
reads them directly; browser access to custom headers is not currently exposed.

## Token quota is not a dollar budget

The application already has [budget administration and ledger-related policy
generation](../services/control-plane/src/aiflux/turnstile_exchange.py), including
budget records and `hard_stop_enabled`. The isolated project policy does **not**
call that ledger. An admin budget record, generated policy text or usage report
does not prove that direct subscription-key requests reserve funds atomically.
This work neither invents prices nor changes that concurrent application code.
Dollar-budget acceptance remains unverified; token quotas do not include separate
safety/PII costs and cannot promise a total monetary ceiling.

**1000 calls is a ceiling, not a promise of 1000 completions.** The unchanged
10000-token daily quota, 1000TPM, output32, safety/PII checks, expiry and backend
availability can reject requests first. No counter reset was requested or issued.

Official references checked 2026-10-26:
[rate-limit-by-key](https://learn.microsoft.com/azure/api-management/rate-limit-by-key-policy),
[llm-token-limit](https://learn.microsoft.com/azure/api-management/llm-token-limit-policy),
[llm-content-safety](https://learn.microsoft.com/azure/api-management/llm-content-safety-policy),
[quota-by-key](https://learn.microsoft.com/azure/api-management/quota-by-key-policy).