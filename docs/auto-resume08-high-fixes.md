# Resume08 — three HIGH corrections, independent audit pending

Status: source06 implementation only; **NOT task complete, NOT approved for
prepare or live use**. Original280, resume05 and retained resume07 are frozen.
No live prepare, cloud reads, scoring, cloud mutation, installation, identity,
secret, certificate or approval is authorized by this document.

## Corrections

1. Finally independently reconciles each owned slot. Offline proves the exact
   revision policy, complete owned metadata/revision flags and fresh strong API
   ETag. Restore proves the exact original/attempted global policy and fresh
   global ETag. A foreign slot is never overwritten and cannot veto cleanup of
   the other owned slot. Both branches are attempted once; unresolved stages
   and reasons are aggregated. Launch still uses the unchanged whole-state guard.
2. Arbitrary verifier execution is removed, including root CLI verifier,
   certificate and reviewer overrides. Manual independent review is supported:
   exact source/fixture binding, exact original receipt hash and parent-approved
   independent identity, plus a recursively pinned native compiler/build receipt.
   Integrity hashes do not themselves establish reviewer authority.
3. There is no socket/HTTP IPC listener or first-client authority. The parent
   supplies its actual native-browser tool invocation and independent inspection
   capability in process. Every call has a new cryptographic 256-bit capability
   bound to phase, origin, exact page URL/id, request id, timestamp, manifest and
   reviewed browser source. It travels only over the trusted native tool channel,
   never a URL, durable receipt or log. Failed attempts are consumed, not retried.
   Actual DOM preflight blocks chat routes and disables Send before safe draft
   fill/End. Score installs the original one-POST route before removing that block.
   Independent parent inspection must corroborate DOM and server correlation;
   self-reported counters or a public manifest digest are insufficient.

## Actual trusted review procedure — no self approval

The next parent assigns a genuinely independent agent/tool audit of the exact
current source-binding and final offline evidence. The implementation author
must not generate a real APPROVED receipt. Test receipts are marked MOCK and
exist only in temporary test directories.

The independent reviewer returns a schema-1 manual receipt with exactly:
schema, reviewer, kind, decision, binding, issued_at, expires_at,
compiler_receipt_sha256, evidence. Evidence identifies original independent tool
results. Kind is nativeSourceReview or packageAudit; decision must be APPROVED,
binding must equal the actual current source/package binding, timestamps are UTC.

The actual parent validates the identity against its preselected independent
reviewer allowlist and pins the exact original receipt SHA256 from that tool
result, not from caller arguments or from the receipt's own reviewer field.
It also pins the original build-provenance receipt digest. That receipt binds
actual compiler/runtime/reference/source inputs and compile argv, fixtures,
DLL/dependencies and semantic outputs. All bytes are rehashed before acceptance.
Source06 native source digest must equal the reviewed source binding. Changed
source, fixture, compiler receipt or DLL invalidates approval. No RSA verifier
is used on this path and no new external signing infrastructure is required.

Only this trusted parent can compose live APIs; the root CLI supports offline
source-binding/localcheck and fails closed for live capability registration.
ParentBrowser must be constructed with existing trusted native-browser invocation
and actual independent page inspection functions, never JSON-selected code. The
parent must retain the original dynamic tool result handle and independently
validate the APIM request correlation and diagnostic one-score/zero-completion
evidence. The browser does not extract credentials or read browser storage.

## Remaining gates

- Parent-assigned independent audit of final source and test/compiler evidence.
- Actual independent source review, parent-owned identity/receipt/build pins.
- Separately authorized fresh prepare and exact independent package review.
- Actual mounted native-browser inspection and server-correlation integration;
  offline mocks do not prove this integration or live scorer acceptance.
- Separately authorized one-score diagnostic with finally cleanup; no retries.
- Production Auto completion and two later chats remain separate and unconsumed.

Budgets remain unused: isolated score 1; diagnostic completions 0; retries 0;
later production Auto chats 2. Validation receipts are exclusive; a failed runner
is retained and never overwritten or described as a successful run.

## Actual final offline evidence

Final exact-source receipts: `.deployment/auto-resume06/highfix10/REPORT.json`.
23 Python tests passed (0 failures/errors/skips), 7 Node tests passed (0 failed),
native compile exit 0, semantic exit 0, 225 expressions and 0 semantic errors.
375 sources bound; 367 protected entries unchanged against both this run's
before-hashes and retained resume07 hashes; original280 changed list empty.
No live prepare/cloud read/cloud mutation/paid call occurred. Editor diagnostics
reported no errors for all six modified implementation/test files.

The highfix08 run passed its tests/compiler but failed report bookkeeping on a
misnamed retained hash file; retained without overwrite. highfix09 passed before
the final challenge-alias/source/deadline hardening; highfix10 validates that
final hardening too. Only highfix10 is the final source audit input.

Next action belongs to the parent: assign independent audit, not approval by
this implementation author. Actual page mounting, trusted tool composition,
dynamic inspection handle/server correlation semantics and live acceptance
remain unproven offline. No task-complete or ready-for-prepare claim is made.