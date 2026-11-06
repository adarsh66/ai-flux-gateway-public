# Resume07 independent audit — NOT READY / no prepare authorized

## Decision

The prior implementation is **rejected for live use**. This audit repaired the
offline compiler runner, so another independent reviewer must review the fix.
No signed approval, private key, certificate or placeholder signature was made.
The diagnostic task is not complete. All actions in this audit are offline.

Retained stage03 evidence: 18 Python tests passed, 4 Node browser tests passed;
native helper exit 1, semantic exit null. The actual error is CS2012: the native
output directory did not exist when csc opened its output. It is not a missing
LINQ import: the native helper and its typed expression fixture already import
System.Linq. The runner now exclusively creates that directory before csc.
The first corrected compile covered 105 expressions, compile exit 0, semantic
exit 0, zero semantic errors. Final validation adds unchanged current22 active
policy expressions. Actual final counts and hashes belong to the durable
report, not to an advance claim in this document.

## HIGH findings (approval blockers)

1. **Cleanup is not independently reconciled by owned slot.** In
   `run_reviewed_window.reconciled`, both policy candidates and the whole guard
   must pass before either cleanup write. Foreign global drift after activation
   therefore prevents offlining an exactly owned diagnostic revision. Conversely,
   foreign revision drift prevents restoration of the exactly owned global slot.
   The existing ownership test accepts neither cleanup being sent. The new
   mock reproduction explicitly verifies the owned revision remains online.
   Required correction: fresh slot-specific ownership/metadata/ETag proofs that
   never overwrite the foreign slot but permit cleanup of the other safe slot;
   retain unresolved evidence for each slot. Do not weaken launch guards.
2. **Verifier executable provenance is outside the review binding.** The CLI
   accepts any verifier DLL; Python accepts its exit 0 and text VERIFIED. The
   shipped native verifier performs RSA verification, but the caller-selected
   executable need not be that implementation. A replacement can accept forged
   signatures. Required correction: reviewer/operator-pinned verifier digest,
   reviewed build provenance and exact source/fixture binding. A reviewer's name
   and certificate hash supplied together by an untrusted caller are not an
   independent trust anchor. Out-of-band operator trust is mandatory.
3. **Native browser IPC result is unauthenticated.** `native_handoff` accepts
   the first loopback connection and returns its JSON. Durable port/binding data
   are readable to same-user processes; a process can submit expected metrics
   without owning the page. A manifest hash is public binding, not authentication.
   Required correction: authenticated parent capability/peer binding and durable
   result provenance, bounded single deadline, and full browser result validation.
   Do not substitute HTTP scoring or inspect browser credentials.

## Reviewed boundaries

- Transport uses one HTTP open per mutation, no retries, pinned CA, redirects
  denied, strong If-Match, only HTTP 200/201, and response/readback ETag equality.
- Attempt markers precede unknown-result writes. Finally attempts cleanup after
  exceptions and expiry; cleanup can reacquire credentials before its operation.
  The slot-coupling finding above means this is not yet a safe cleanup guarantee.
- Package manifest hash binds exact candidate/artifact/source hashes; renderer
  reproves one global condition and three revision attributes. Active current22
  policy stays byte-identical. Root130/49 keyed checks, local child191, all79 roles,
  full22 deployment metadata, four settings and inheritance are guarded. Child
  proof is local, not a remote-child claim. Frozen original280 and resume05 must
  remain unchanged; report records actual comparisons.
- Auto defaults/fragments are taken from the retained original corpus. New9
  explicit models may not enter the original Auto pool. This diagnostic is not
  permission to change the old6 candidate pool, defaults, fragments or routing.
- Native bridge retains its catch-all one-POST route; fixed one-user-message body,
  gpt-5.4-mini, no system/history, one Control+Enter, revision2 rewrite, sanitized
  response, no auth/header/storage inspection. Current Node tests mock page APIs;
  they do not prove actual mounted browser IPC or successful live scoring.
- Native C# fixture compilation is semantic compilation against installed .NET
  and Newtonsoft types. It is not APIM service policy validation or execution.

## Exact source-review protocol (NOT an approval)

Entrypoint module: `scripts.deployment.auto_resume06_parent`.
Read-only offline argument: `source-binding` returns the exact binding.

Future **blocked** prepare arguments are `prepare --package <absolute-new-path>
--review <absolute-envelope-path> --reviewer <out-of-band-reviewer-id>
--certificate-sha256 <out-of-band-DER-certificate-sha256>
--verifier <absolute-reviewed-Resume06Native.dll>`.
Package parent must be `.deployment/auto-resume06/packages` and its fresh basename
must start `auto_resume06-`. Never reuse a retained package. This audit invokes
neither prepare nor live transport.

Envelope has exactly payload, signature and certificate. Payload has reviewer,
kind nativeSourceReview, decision APPROVED, binding equal to actual source-binding,
issued_at and expires_at UTC. Signature is base64 RSA PKCS#1 v1.5 SHA256 over UTF-8
JSON payload with sorted keys, compact separators, allow_nan false (Python default
ensure_ascii true). Certificate is base64 DER, key size at least 2048; its SHA256
must match a genuinely independent operator trust anchor. No locally invented
certificate/signature can establish independent review. Exact binding is retained
under validation01/nativeSourceReview-binding.json for the final source snapshot.
Source changes invalidate it. Fix HIGH findings before requesting approval.

Later packageAudit separately binds manifest_sha256, sources, artifacts and
browser_observation_sha256, with fresh real native browser observation. Source
review is not package approval. Mounted preflight currently expires in 30 seconds;
multi-stage capture/activation can exhaust it and must then fail into cleanup.

## Expected future diagnostic write surface and budgets

ARM APIM scope (subscription aa28274d-fea0-46d4-b9c8-30f3ef0a0e52):
resource group IDS-TOKEN-EXCHANGE-POC; service poc-ids-token-ex-apim.

- PUT service /policies/policy?api-version=2024-05-01 (install global).
- PUT service /apis/aiflux-dev-unified;rev=2/policies/policy?api-version=2024-05-01.
- PATCH service /apis/aiflux-dev-unified;rev=2?api-version=2024-05-01
  with properties.isOnline true, then finally false.
- PUT original global to the same global endpoint during finally.
- One native browser POST rewritten to
  https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1;rev=2/chat/completions;
  diagnostic policy sends at most one scorer request to
  https://poc-ids-token-ex-foundry.services.ai.azure.com/providers/microsoft/v1/systemone.

Maximum window 30 minutes; inclusive 22-minute launch/cleanup reserve checked by
UTC and monotonic clocks before launch. Durable global ledger is
.deployment/auto-resume06-isolated-score-owner.json, exclusive across packages.
Budget: one isolated score, zero completions, zero retries; two later Auto chats
remain separately authorized and unconsumed. No ledger deletion/reset/replay.

Next parent: read actual report and repro, resolve findings, obtain another exact
source audit, then genuine signed review. **Not READY FOR ONE fresh prepare yet.**