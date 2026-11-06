# Resume09: external native-tool handoff

Implementation scope: executable **read-only integration**, not live authorization.
No approval is issued by this implementation. Original280, retained05/07 and all
highfix10-bound bytes remain unchanged. The successor never calls06 `prepare`,
`ParentBrowser`, a listener, or a caller-selected executable/verifier.

## Supported external await protocol

The Python CLI is `scripts.deployment.auto_resume09_handoff`. It exits at each
boundary. The outer VS Code parent runs its real browser tool **between** CLI
calls; no Python callback pretends it can call that tool. Its source is an actual
self-contained async function using only supported `page` read APIs, not a
JSON serialization of functions with unresolved module closures.

1. `localcheck`: hash actual original280/highfix10/resume07 protected sources and
   all retained05/07/highfix10/live01 files. The06 dynamic source glob now sees
   successor files; that is NOT a reason to refresh its historical binding.
2. `mounted-begin --folder <absolute new auto-resume09/mounted-NAME>`: exclusively
   create manifest, observe request and executable observe-tool.js. No window,
   prepare, score budget, mutation, route hook, fill or keyboard event is created.
3. Parent reads that exact generated tool body, checks page/source/manifest/time,
   and executes it through its actual `run_playwright_code` on the pinned page.
   Parent retains the ORIGINAL native result handle, independently pins its
   result bytes, and exclusively writes the finite result envelope. Envelope
   fields: tool, tool_result_handle, page_id, result (the original sanitized
   probe result). No key, token, storage or raw DOM snapshot belongs in it.
4. `accept-result --phase mounted-observe --folder ... --result ...
   --result-sha256 ... --original-tool-handle ...`: consumes acceptance **before**
   validation, checks bytes, bindings, freshness, exact22 named models and blank
   conversation. Emits a separate inspect request and executable tool body.
5. Parent executes that second read-only body in a NEW native tool invocation,
   independently inspects the mounted page, retains its distinct original
   handle, pins the original output, then uses `accept-result --phase
   mounted-inspect` with those original pins. Same-handle corroboration fails.
6. `cleanup --folder ...` closes this read-only handoff exclusively. It does NOT
   claim remote offline/restore occurred. Closed/expired/failed requests cannot
   be accepted again. Partial files and failed attempts are never overwritten.

Hashes, arbitrary CLI handle strings and writable local files are NOT native-tool
authority. A caller can forge local test JSON; these acceptance receipts grant
**no live authority**. Only the actual outer parent can independently compare
original tool output. No automatic cryptographic attestation from the VS Code
browser tools is available. Offline tests explicitly use MOCK fixtures.

## Finite live boundaries and precise missing guarantee

`prepare`, `install`, `activate`, `reserve-score` are executable refusal
boundaries, before ANY capture/window/claim/mutation. No JSON approval or watchdog
flag can bypass them. This is intentionally not a purported complete live runner.

Live requires independently audited09 source/compiler provenance and package
approval with original parent identity/pins; fresh complete protected captures;
the unchanged inclusive22-minute reserve; independently enforceable expiry
cleanup; a reviewed one-POST tool integration and separate server corroboration
proving one score and zero completion. The read-only probe proves none of those.

There is **no currently implemented off-laptop cleanup supervisor**. Python
`finally`, a local worker/thread, an expiry timestamp or a parent promise cannot
guarantee cleanup while a native tool awaits, after laptop loss, or with expired
credentials. A remote independently executing supervisor needs separate approved
deployment/identity/ownership, immutable reviewed inputs, durable one-attempt
intents, bounded timeouts, ownership-aware fresh ETags, slot-independent
offline/restore attempts and failure reconciliation. None is created here.
Without it these live boundaries must stay blocked. Even a remote supervisor
cannot promise successful writes during an Azure/network outage: distinguish
independent cleanup *attempt responsibility* from guaranteed cleanup *success*.

Any eventual successor must reuse the **existing global06 score owner path**,
not mint a09 budget. Claim it with exclusive creation BEFORE any live effects;
partial/uncertain old claims remain consumed. Reserve once, no retry. Cleanup
must reconcile each owned slot independently; foreign global must not veto an
owned revision offline, and foreign revision must not authorize its overwrite
or block owned global restore. No arbitrary verifier/certificate/executable,
no listener/first-client trust, no self-reported counters as authority. These
three HIGH fixes are not weakened by this handoff.

## Original06 lifecycle findings

- Start/end freeze a 30-minute window only after preparation captures. The
  inclusive22 reserve permits just eight minutes for later review and startup.
- Three installs each perform a pre/post full capture (**six**), followed by an
  extra pre-score full capture. A capture has a180-second reader deadline, but
  credential acquisition and some commands/root reads occur outside portions of
  that deadline; this is not a proven total wall-clock maximum. Six captures
  alone can exceed the eight-minute allowance. Reserve must NOT be lowered.
- A browser preflight must remain less than30 seconds old even after all this
  work. The original observation timestamp is reused before scoring. Ordinary
  capture duration can make a correctly authenticated preflight stale.
- A post-call elapsed-time check detects late return but cannot interrupt a
  stalled external native tool. Finally executes only when control returns.
-06 browser output uses stringified function bodies with free module state
  (`leases`, sourceHash, nativeSource). It is not itself a runnable standalone
  VS Code browser-tool body.09's read-only body has no such dependencies; this
  does not certify the old live one-POST bridge.

Next parent actions: independent source09 review, actual two-call mounted probe
with original pins, then resolve remote cleanup ownership and review a separate
live successor. Do NOT invoke fresh prepare or Send on this implementation.