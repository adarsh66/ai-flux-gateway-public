# Auto path diagnostic — executable review-gated release

The production adapter and explicit CLI are implemented and offline tested.
This is **not deployed, activated, independently reviewed, or browser tested**.
Preparation is read-only and never chains activation, Terraform, build or Send.
Historical controllers, manifests and diagnostic06 remain unchanged.

## Preparation

- Run the offline Python tests, 68 proposal CORE tests and native successor plus
  timer-free browser06 tests first. The historical diagnostic06 source-binding
  test is a SEPARATE known failure after the customer Send UI release, not a
  new-test regression. Never restamp that manifest. No Vite/esbuild/build/apply.
- `prepare` requires `--package`, `--tests`, `--browser-tests`, `--proposal-tests`.
  The package must be NEW, auto-path-diagnostic-prefixed, directly under the
  existing deployment evidence root. All actual clean receipts are hash-bound.
- Explicit `prepare` reads a NEW full13 snapshot, all four settings hashes,
  supplemental security metadata, storage hash, project state185, runtime111
  identity/hash/ETag, current1 and rev2 flags, both global and revision policy
  formats and inherited policy/product/subscriber/operation/diagnostic metadata.
  Existing appsettings/list POSTs are metadata reads, not configuration writes.
- It never compares against/reset-adopts the old pre-cm38 full13 baseline.
  Customer must retain digest5f55… and API digest29b67…; all other fields are
  bound from actual fresh reads. No values/tokens/state resources are printed.
- Freeze the <=30-minute UTC interval ONLY after tests and fresh capture.
  Check fractional-second freshness BEFORE rounding the policy UTC seconds.
  Hash actual runtime state bytes in memory; no state file or Terraform command.
  Every package/artifact/attempt uses exclusive creation, flush and fsync.
  Never refresh or overwrite an existing package to extend its interval.

## Policy and C# correctness

Reuse the immutable Node proposal. Its global output contains the *observed
extra export entity layer*: it is NOT a valid wire representation to send
unchanged. Parse this layer, independently compare the complete decoded C#
predicate, prove only the finite guard delta, then serialize standard XML once.
Verify rawxml and xml exports against the complete expected tree independently.
No claim of actual APIM C# compilation follows from XML/offline tests.

The exception is fixed to trusted APIM API identity, revision2, POST, product,
subscriber, source167.103.66.248 and the two exact OriginalUrl representations.
No base removal, URL rewriting in policy, header spoofing, broader path/IP or
safety/quota bypass. Existing fixed-body, redaction, safety, scoring terminal and
one-call/3600-second quota remain; a fresh counter denotes **one new budget**,
not an assertion about historical scoring request counts. Completion budget0.

## Actual parent review and explicit execution

The parent must actually review **all six** stages: install-global,
install-revision, online, reserve, offline, restore-global. A manifest hash,
review-after-preparation timestamp, exact stage list, and retained independent
native review transcript/hash are mandatory. The receipt also requires
`parent_says_cleanup:true`. Never generate a fake approval. No cleanup review
can be deferred until after activation or browser interaction.

`ProductionAdapter.capture` uses strict existing full13/settings metadata reads.
`last(stage)` does NOT invoke a second full capture. It rereads exact current
and owned metadata, all revision flags and BOTH formats of BOTH policies, then
the exact mutation target. It returns the SAME capture with the actual final
target-read timestamp and revalidated opaque ETag. Global reads target the APIM
SERVICE, never an API. The target must be less than30 seconds old. Its token
stays in memory and is reused rather than acquired after the freshness check.

Exact body/hash, stage, manifest, review and ETag must match a permanent fsync
intent. The spawned writer uses one verified corporate-CA opener.open with
45-second socket timeout and60-second parent watchdog, no retry/redirect/SDK
polling. It returns HTTP status or a FIXED failure label only; no response body,
arbitrary exception, token or header output. An existing intent ALWAYS forbids
replay, even after errors/timeouts/crashes. Complete independent after-reads
are retained and hash-bound in verified receipts.

Explicit commands (never chained from prepare):

- `localcheck`: local source/artifact/test integrity only, no live-state claim.
- `activate`: once-only install-global, install-revision, online after real
  all-stage review AND actual safe browser preflight. Never invokes a browser.
- `reserve`: creates the durable parent browser intent BEFORE capture/shared
  ownership; verifies activated state and completes independent after-reads.
- `claim`: separate fast LOCAL command after reserve. Verifies manifest,
  review, intent, shared owner, reservation, nonce and browser-source bindings.
  Permanently consumes the claim and emits browser-binding.json. Its30-second
  clock starts HERE, not before six lengthy activation captures. Never renew.
- `cleanup`: expiry-independent reviewed offline, THEN original-global restore.

The activation supervisor attempts the separately reviewed
offline and restore-global stages once if activation fails after a global
intent. Cleanup failure records UNRESOLVED and stops; it never retries an
existing cleanup intent. These are offline-tested, not actual rollback proof.
Fresh original/candidate content decides after an unknown global install result,
not success receipts. Ambiguous cleanup requires fresh reads, NEVER replay.

Cleanup is independent of failed next-stage receipts and window/review expiry.
It accepts only exact originals or exact installed candidates; any other content
or ETag drift stops, never clobbers concurrent policy changes. Restore-global
requires independently verified offline first. Compare original/candidate via
`c.tree`/`c.signature`, NOT fragile wire-byte/export-byte equality. Match complete
known raw C# attributes AND text and verify the entire remaining tree. Preserve
the independently bound raw full13 global hash; only that separately checked
field may change. Revision diagnostic may remain installed but offline.

If already offline/original global, record permanent intent and `no_wire:true`
result, send NO PATCH/PUT, and perform independent fresh after-verification.
Unknown policy/ETag/protected-state drift stops instead of overwriting changes.

## Browser ownership

The separate successor
[scripts/deployment/auto_path_diagnostic_browser.mjs](../scripts/deployment/auto_path_diagnostic_browser.mjs)
exports standalone timer-free source retaining browser06's one-attempt body,
route, response and retained-closed guard. Adds new scope/correction/nonce,
review and claim bindings. Changes browser URL only, never headers/body. The
first POST consumes the attempt, including invalid requests; later POSTs abort.

Before activation, the parent must actually observe safe real UI events with
NO Send, retain the sanitized actual result, and supply browser-preflight.json:
`evidence`/`evidence_sha256`, package browser-source.js `source_sha256`, exact
`manifest_sha256`, full actual `page_id`, actual `at_utc` under30 minutes old,
`parent_observed:true`, `safe_events_observed:true`, `fixture:false`,
`send_invoked:false`. These are actual-parent attestations, not conclusions
inferred from successful tool calls, Node/VM tests or abort-only fixtures.
Blank/signed-out/unresponsive pages are NOT ready. Never inspect credentials,
auth storage or keys. No preflight or approval is fabricated during preparation.

Parent invokes the exact source with the real binding once within30 seconds of
claim and with90 seconds still reserved before expiry. Parent owns finally
cleanup and actual browser receipt retention; keep the closed interceptor until
independent offline verification. Crash/laptop shutdown cleanup is NOT guaranteed.
HTTP metadata alone is not scorer/schema proof. Historical count stays UNKNOWN.

## Evidence classification

Actual Python production tests, native browser tests, proposal CORE and the
known historical binding failure have separate retained receipts. Early syntax
or fixture failures stay retained, never overwritten. The old diagnostic06
Playground binding does not cover the current customer source; this successor
binds current source explicitly. Clean test receipts are NOT independent native
review, APIM compilation, live MI/scorer proof or deployment acceptance.