# Additive deployment continuation — partial acceptance, standalone preflight stopped

## Standalone API attempt02 — actual stop, 2026-10-31 14:15:47 UTC

The newly authorized one-shot standalone controller reserved its exclusive
[durable ledger and report](../.deployment/auto-additive-buildplan01/standalone-api-attempt02/REPORT.json).
**Actual inference sent count: 0. No HTTP inference status, answer, selected model,
or completion/decision token usage exists for this attempt.** The reservation is
consumed and was not replayed; no scoring or completion request was made.

[Fresh full pre-request guards](../.deployment/auto-additive-buildplan01/standalone-api-attempt02/pre-guards/REPORT.json)
passed: root132/child193, all22 advertised models/backends, exact full state,
settings/image pins/roles/security/network, all eight policy readbacks and revision
statuses, backend unlocked with unchanged ETag. These are configuration proofs,
not an explicit22 runtime matrix or a global quality claim.

The existing authorized client acquired current CLI authentication and inspected
the fixed subscriber. Its active-state and expected product-scope assertions
passed. The subsequent product-read HTTP200-and-published predicate failed with
`product_not_published`; the controller did not retain the product response, so
the receipt does **not** distinguish non-200 from a non-published product state.
It stopped before listSecrets/key retrieval and before creating the send intent.
No permission grant, new subscription, key rotation, browser credential extraction,
cloud write, build, plan, apply, inference retry or rollback occurred. Keys/tokens
were not printed or persisted. TLS used the pinned corporate CA with verification.

The original worker completed; blank terminal output was not treated as success.
The prior browser greeting success below remains separate historical evidence.
Standalone acceptance remains incomplete. Any further attempt requires explicit
new authorization; this consumed reservation is not a retry ticket. No automatic
disableAuto write was performed for an unsent preflight stop.

## Actual acceptance evidence — 2026-10-31 14:04 UTC

**Acceptance remains incomplete; task not complete.** The original
[browser attempt](../.deployment/auto-additive-buildplan01/browser-acceptance-attempt01.json)
completed once: **“Hi, nice to meet you!”**, selected **DeepSeek-V4-Flash**, balanced,
no fallback, completion usage **12 input / 8 output / 20 total**. The actual shared
Playground still displayed that result and **22 explicit models plus Auto**.
Parent reports authenticated availability ready=true; no readiness request was
replayed here. Runtime verification/publication flags were not changed.

The existing [decision-overhead KQL result](../.deployment/auto-additive-buildplan01/acceptance-readonly01/evidence/decision-overhead-result.json)
contains one matching persisted decision between **13:51:00Z and actual now
14:03:30.599521Z**. At **14:00:46.7163857Z**, request
**0a4d669b-9913-4bac-9ace-79ce1e5cf1fe** has parent HTTP200, parent4499ms,
balanced/DeepSeek-V4-Flash, config
**10359b8e7939683fa239c04eefb840a9e21080c1cfed0ac62631ba8ee554fe8e**,
one decision event, decision latency **1513.0733ms**, and decision usage
**4251 input / 1 output**. Decision cost is **null/unknown, not zero or free**;
decision usage remains separate from completion usage.

MI scoring HTTP200 is supported by **policy-bound evidence**, not a separately
captured scorer response: the [exact active policy](../.deployment/auto-additive-buildplan01/gateway-final-native-policy.xml#L531-L646)
authenticates scoring with managed identity, requires HTTP200 and valid scoring
output, and returns503 before emitting the validated decision event on failure.
Fresh readback matched that exact policy. One record matches browser alias,
profile and config, and precedes its durable ledger timestamp by about seven
seconds. **Exact browser-to-request-ID correlation is not proven**, because the
original browser ledger contains no request ID or exact send timestamp.

[Fresh full guards](../.deployment/auto-additive-buildplan01/acceptance-readonly01/evidence/REPORT.json)
passed at **14:04:12.922648Z**: root132/child193, full exact state, all22 advertised
aliases and backend hashes, all eight policy readbacks, revisions1current/online
and2offline, all four settings maps, image pins, roles/security/network unchanged,
and closing backend unlocked with unchanged ETag. This is configuration protection,
**not a paid explicit22 runtime matrix**.

**The remaining direct API test was not sent.** The official key-reveal flow
requires portal-user authorization; this session has no supplied supported
noninteractive portal credential. The signed-in browser uses local portal auth;
its session token/key was not extracted from storage, application state or
network headers. No admin Key Vault secret was read, management credential
substituted, JWT invented, key logged/exported, browser Send substituted, or
model request made. [Preflight](../.deployment/auto-additive-buildplan01/acceptance-readonly01/evidence/direct-api-preflight.json)
retains the unsent balanced math request with stream=false and completionlimit16;
the exact policy permits integer limits1–1024, further bounded by candidate limits.
**One end-to-end attempt remains**, requiring an exclusive durable send ledger
before any future POST; unknown outcome consumes it, retries0.

No rollback was triggered: auth-unavailable preflight is not a failed model test,
and no explicit-model regression was observed. No cloud writes, build, apply,
database/network/role changes or acceptance-flag changes occurred. Azure helper
403 and AppLens422 were not bypassed; documented troubleshooting was consulted,
and installed CLI credentials plus pinned corporate CA/strict TLS were used for
the successful bounded read-only log query and guards. See the
[acceptance assessment](../.deployment/auto-additive-buildplan01/acceptance-readonly01/acceptance-assessment.json).
No routing-quality, general reliability or free/known decision-cost claim is made.

The earlier sections below are preserved historical checkpoints, superseded by
the actual deployment/readiness/partial-acceptance evidence above.

## Settings-only plan prepared — 2026-10-31

Actual [saved plan](../.deployment/auto-additive-buildplan01/settings-activation03/settings-only.tfplan)
SHA256 d732ea24095d4e31e05a476e14b58c9a795a2a4aecd2101039ebf0857327b5ff.
[Local review](../.deployment/auto-additive-buildplan01/settings-activation03/PLAN-REVIEW.json)
and [parent Explore request](../.deployment/auto-additive-buildplan01/settings-activation03/REVIEW-REQUEST.md)
are now available. No apply. Independent settings review and official/native predicate
validation remain pending, not fabricated. Parent can review the actual artifacts now.

[Exact diff](../.deployment/auto-additive-buildplan01/settings-activation03/exact-settings-diff.json):
one API settings update, five additions; all44 existing Terraform settings preserved,
all47 existing ARM settings preserved including three provider-owned registry values.
Six supported fields do not mean six additions: PUBLICATION_PATH remains absent while
PUBLICATION_JSON delivers the actual schema2 receipt. All image pins and other API
attributes remain exact; no creates/deletes or unknown API attribute changes.

[Publication](../.deployment/auto-additive-buildplan01/settings-activation03/publication.json)
uses real final-native policy, actual distinct ARM-readback, authorization, prior
parent-reported release-review and [rollback](../.deployment/auto-additive-buildplan01/settings-activation03/rollback.json)
hashes. Prior review provenance is explicit; it is NOT a new settings-plan review.
runtime_verified=false. Budget2/2/2, retries0, fallbackfalse; no paid calls or Send.

Parent-reported actual shared-browser supported ingress returned JSON404 NotFound
for /api/health and JSON401 Access token required for /api/auto-routing/availability;
Playground had22 authenticated explicit options. This proves actual API reachability
through existing portal proxy and new endpoint authentication protection, NOT authenticated
availability readiness or scorer/runtime proof. Direct403 IpForbidden is EXPECTED
existing ingress, not a regression or prerequisite to opening any network boundary.
[Evidence scope](../.deployment/auto-additive-buildplan01/settings-activation03/supported-ingress.json).

Actual retained and postplan root131 content matches, child193 unchanged, backend
unlocked. Terraform plan lease changes ETag; exact content was independently verified
rather than assuming unchanged metadata. Fresh full protected preapply guards remain
required. Original pre-plan/no-op/local-check failure receipts are preserved, no replay.
The older blocked assessment below is historical and superseded on transport/review
availability; it remains preserved as the original observation.

## Latest actual continuation — 2026-10-31 13:30:49Z

The original login PID28164 completed on the expected tenant and subscription
after accepting its existing subscription-selection default. No new login.

[Latest durable report](../.deployment/auto-additive-buildplan01/finish-additive/final05/REPORT.json)
supersedes the historical authentication blocker below. Actual root serial131
matches only the saved API image transition (both full and registry-relative
representations); all49 check statuses and objects match the saved plan exactly,
including null unknown objects. Child serial193 unchanged. Full protected state,
all22 models/backends, four settings maps, other image pins, roles/security/network,
all eight exact policy-format readbacks and revision statuses passed. Closing
backend HEAD200 was unlocked with the same ETag as the captured root.

API direct health returned **403 Ip Forbidden**. No health retry, firewall change,
model request, Send, build, image/gateway apply replay or cloud mutation occurred.
No production regression was established; no rollback was performed.

Activation is **not browser-ready**: actual independent Explore/subagent review
is unavailable in this session, and direct health cannot be established from
this host without changing an explicitly protected network boundary. No review
was invented, publication constructed, settings plan generated or settings applied.
Actual reviewed schema2 settings-only publication and approved-origin health remain
required before parent-owned two-attempt acceptance. runtime_verified remains false.

Two local checker failures were preserved: null unknown check objects and the
registry-relative Terraform docker_image_name. Separately named missing-only
continuations proved the exact saved projection, retained the successful root GET
under unchanged ETag, and never replayed consumed production reads.

## Historical authentication checkpoint (preserved)

## Durable outcome

[Final report](../.deployment/auto-additive-buildplan01/finish-additive/FINAL-REPORT.json).
No production reads or writes, model requests, Send, build/test replay, gateway
reapply, API image reapply, or credential export occurred in this continuation.

The gateway was already applied once. Its retained
[full guard](../.deployment/auto-additive-buildplan01/gateway-guard13/REPORT.json)
proves exact decoded expressions, exact XML/rawxml readbacks, all22, full security,
revision1 current/online and revision2 offline. The transport proof is actually
[transport-proof.json](../.deployment/auto-additive-buildplan01/transport12/transport-proof.json),
not an assumed REPORT file. These are retained observations, not fresh API postguards.

The API cm4g image was already installed once, exit0 at13:11:21Z:
[actual receipt](../.deployment/auto-additive-buildplan01/api-install14/APPLIED.json).
Postguards remain pending. No rollback was indicated: no production regression
was observed and this continuation did not mutate production.

## Exact blocker and original process

The [first guard stop](../.deployment/auto-additive-buildplan01/finish-additive/REPORT.json)
was the pinned credential predicate before any ARM/storage production request.
A secret-free diagnosis found tenant/operator/audience matched but only490 seconds
remained, below the required600. The guard was not weakened.

One normal tenant-scoped Azure CLI login was started with the existing corporate CA
bundle; no force-refresh loop, TLS bypass, alternative identity or exported token.
The terminal interface returned blank, so execution was not assumed complete.
An actual local task subsequently identified **original login PID28164**, parent16408,
created2026-10-31T21:18:39.229672+08:00, still running. Complete its sign-in directly
in the existing terminal/sign-in window; do not launch another login.

The same continuation worker's only unconsumed postguard launch (PID26016) stopped
exit1 on that original login worker before credential acquisition/production reads.
Its [actual report](../.deployment/auto-additive-buildplan01/finish-additive/completion/REPORT.json)
and [worker guard](../.deployment/auto-additive-buildplan01/finish-additive/completion/postguards/workers-before.json)
are preserved. No worker was killed or allowed past an unknown-process guard.

## Remaining work, not claimed complete

After the original login finishes: continue the existing
[worker](../.deployment/auto-additive-buildplan01/finish-additive.py) only for missing
fresh API full guards/current root and child/all22/unchanged settings and other
image pins/revision status/exact policy formats/actual HTTP health. Review any
state-check transitions explicitly. No existing apply or old plan replay.

Read the already-built [publication contract](../.deployment/auto-additive-buildplan01/api/modules/auto_snapshot.py)
for actual schema2 fields. Construct inline receipt only with actual authorization,
independent review, final policy/readback, source-defaults and rollback bindings;
runtime_verified=false, budget2 attempts/2 scoring/2 completions/0 retries/no fallback.
No publication has been constructed or settings plan generated in this continuation.
The new settings-only plan still requires exact local review, actual independent
review, relevant official validation and fresh preapply guards. Explore/subagent
execution is not available in this session; no independent review was fabricated.
Authenticated browser availability and bounded parent acceptance remain pending.

Azure guidance was consulted. The CLI helper returned403 and its troubleshooting
guide was read; the already-installed CLI was used without installation or security
changes. No corresponding new resources exist for quota/CAF/KeyVault provisioning
rules. No roles, networking, DDL, images or Terraform configuration were changed.