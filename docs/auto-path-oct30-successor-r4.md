# Unbound r4 — startup bottleneck correction, not release authorization

Separate module/fixtures only. Never edit the 265 files frozen by stopped
manifest 7d54f350d05e6139dd5d1b871c97a925256a5533b2d7b298ddf7ac38601bb75a.
PID27920 stopped at 07:48:01Z without activation/window/stage intents or writes.
Do not retry that attempt. No prepare/window/cloud reads or writes are requested.

## Measured cause and bounded correction

The retained attempt's review-to-rejection cost was 157.8s, missing the
07:47:07Z launch cutoff by 54.3s. The offline cProfile receipt
[existing-r3 profile](../.deployment/oct30-r4-existing-r3-profile.txt) measured
one real localcheck: 82.246s cumulative, 3 latest and 17 older predecessor
checks, 370 verify_formats calls (52.924s cumulative), 29 subprocess calls.
Profiling adds overhead; these are measurements, not future latency guarantees.
The existing CLI main.checked_package, run_parent.checked_package,
run_parent.review and run_reviewed_window.review each call localcheck before
the launch guard. Merely starting the parent once does not remove that work.

R4 privately derives the existing controller and parent. Its only changed
deadline is remaining >=22min (inclusive), allowing at most8min startup in a
fixed30min window. 23min passes, 21min fails. Planning allowance: observed
activation ~14min + reserve ~4min + binding/handoff up to30s + unchanged90s
final-stage reserve = ~20min, leaving ~2min uncertainty. This is not a promise
that slow live reads will fit. The actual stage gates still fail closed.

Pure format validation alone is memoized per process, max256 entries, keyed
by the entire canonical pair (including metadata) and exact optional wire
bytes. Failures are not cached; returned XML trees are deep copies. Changed
bytes get full validation. No file, hash inventory, source list, receipt,
render, review, clock, ETag, owner, intent or cloud capture is memoized.
All complete SHA checks still execute on every localcheck and per stage.
There is no disk cache or cross-process proof adoption.

## All remaining gates are inherited unchanged

- Prepare captures full13 before freezing one UTC window, length <=30min.
  New packages must use the exclusive auto-path-oct30-successor-r4- prefix.
- Parent all-six review/transcript and real current browser preflight/page
  bindings precede startup; no old review or fixture becomes real approval.
- Every noncleanup review, including the second review after final-target
  revalidation, requires start <=now <end-90s; review/preflight age <30min.
- All before/after full13 reads, both formats, exact ETag/If-Match, last-target
  freshness <30s, permanent exclusive intents, no retries/redirects remain.
- Reserve keeps its parent intent, full before/last/after reads and owner.
  Claim requires verified reserve age <2min and now <end-90s. Binding is30s;
  the callback requires20..30s remaining and is bounded by the fixed end.
- Scoring1/completion0/retry0, fixed IP/text/model/path and policy expiry
  are untouched. There is no new writer or activation/reserve/claim CLI.
- Existing finally is armed before activation; failures clean once only if
  install-global has an intent. Cleanup remains independent of expiry,
  requires fresh full13 and offline-before-restore, never replays intents.

Recommended future entrypoint: module
`scripts.deployment.auto_path_oct30_successor_r4`, existing parent CLI
`prepare`, `localcheck`, `run-reviewed-window`. No current manifest, approval,
page or runnable release command is supplied. A later explicit authorization
must name a NEW package; old7d54 remains stopped. Offline temporary fixtures
and source review are not live package approvals or browser evidence.