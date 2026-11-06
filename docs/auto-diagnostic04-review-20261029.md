# Diagnostic04: one package, one activation, parent-owned browser

## Actual checkpoint — 2026-10-29 08:30 UTC

**Auto is NOT enabled on the customer-serving route.** The reviewed04 policy
PUT and online PATCH each returned200; the original activation reached
ONLINE_READY at08:12:30 with a durable one-request browser reservation.
The parent invoked normal Send once. Playwright timed out waiting for the
button to be visible/enabled/stable; no scoring response was obtained.
The URL-only interceptor was removed in `finally`. No Send retry occurred.
The timeout alone does not establish zero requests or a successful score.

Parent explicitly authorized cleanup. Its single offline PATCH returned200
at08:16:35. The controller's post-write capture timed out; this did NOT
authorize another PATCH. Separate read-only reconciliation completed at
08:30:02 and proves revision2 offline/noncurrent, revision1 unchanged/current,
all13 protected components and supplemental/inherited controls exact, and
state185 unchanged. Four documented settings/list POSTs were read operations,
not mutations; values were not logged.

Actual [complete verification](../.deployment/auto-offline-revision-20261029T060302997824Z/diagnostic04-full-readonly-20261029T082900768569Z/result.json)
and [browser attempt](../.deployment/auto-offline-revision-20261029T060302997824Z/scoring-diagnostic04/browser-attempt-result.json)
are retained. Do not replay04 activation, Send, cleanup, or historical plans.
Controller-local zero request counters are NOT gateway telemetry and cannot
establish whether a browser request reached the scorer. Actual gateway-MI
scoring/schema proof, production policy acceptance, separate persisted decision
telemetry, immutable application releases and default-onboarding end-to-end
acceptance remain unfulfilled. No new tenant/admin approval gate or DDL is
authorized by this checkpoint.

## Historical preparation contract

Prepared locally only. No cloud mutation is authorized before the independent
native parent review. The manifest freezes a new 20-minute server fail-closed
scope; it cannot be renewed in place. The nonce, counter limit one, scorer-only
terminal, zero completion calls, fixed text, subscription, source IP, path and
all inherited security policies remain unchanged.

## Concrete diagnostic03 fault and correction

Actual diagnostic03 online PATCH returned HTTP 200 and full readback verified
online/noncurrent. A second controller invocation was wrongly submitted after
silent terminal output. Its exclusive guard prevented a second wire attempt,
but its shell failure-cleanup branch took the revision offline before browser
reservation. The actual sequence report records zero browser Sends/scorer calls.
Diagnostic04 binds actual03 PUT receipts, online/offline intents and readbacks,
the deviation report, historical source and every retained scoring-package file.
It does not pretend diagnostic02 or the history inside manifest03 is current.

The adapter uses the existing capture and PATCH executor, not an arbitrary
controller clone. It changes the policy predecessor to actual03, adds one
exclusive activation-owner intent before work, and provides one combined
activation that returns immediately after reservation. No finally/failure
cleanup exists. Parent review covers all four scopes in one receipt.

## Parent review and execution contract

Module: scripts.deployment.auto_diagnostic_window04.

1. Review exact source/tests, manifest, historical receipts, XML time-only delta,
   literal offline PUT and online/offline PATCH bodies in one independent native
   review. Retain its real transcript in the package. Create parent-review.json
   with approved=true, independent_native_review=true, stages exactly
   [policy-put, online, reserve-browser, offline], exact manifest_sha256, at_utc,
   transcript (package-relative), transcript_sha256. Never fabricate a review.
2. Invoke stage `activate` **once**. It owns the sequence offline PUT -> online
   -> reserve-browser and returns `ONLINE_READY` immediately, without Send or
   cleanup. Each scope retains its own exclusive single-wire intent/result.
3. If terminal output is silent, do NOT invoke activate/online again. Read the
   existing exclusive intent/result using stage `status` (local only) and wait
   for the existing worker notification. A failure is not retry authorization.
4. Parent uses its existing normal authenticated browser page and performs at
   most one Send only after the actual04 reservation. No executor browser work,
   authentication/header/storage inspection, direct scoring or completions.
5. Only when parent says cleanup, retain cleanup-authorization.json with
   parent_says_cleanup=true, manifest_sha256, review_sha256 and at_utc. Invoke
   stage `offline` once. The server window and review may have expired; cleanup
   deliberately has no expiry guard. Full ownership/source/history/state185/
   current rev1/all13/security checks still apply. No automatic cleanup while
   waiting for parent, no re-online after any cleanup intent.

No Terraform state writes, role/network/image changes, current-revision switch,
build or inference are part of preparation. Historical online/offline attempts
are consumed, not repeatable; historical zero Sends leave one overall browser
budget, not a new budget per window. Path inheritance may still safely return
403; no inherited-policy bypass is permitted.