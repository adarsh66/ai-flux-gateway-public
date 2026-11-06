# Parent review handoff — one-shot direct ARM revision2 correction

## Disposition

Preparer only. No PATCH, Terraform command, live discovery, scoring request,
policy write, Auto activation, image build, role or network write is performed
by preparing this package or running its fixture tests. No independent review
has been performed by this preparer. The parent is to call its **native
independent reviewer** on the exact manifest, source, fixtures and this handoff.
This document supersedes the earlier *Python-path* retry blocker, not any
retained provider evidence: provider replay restrictions do not apply to the
separate explicit no-retry urllib transport.

## Exact operation

- [New source](../scripts/deployment/auto_revision_arm_once.py) and
  [offline fixtures](../tests/unit/test_auto_revision_arm_once.py).
- Existing subscription aa28274d-fea0-46d4-b9c8-30f3ef0a0e52, tenant
  beb276ac-6e9f-498e-8e31-019ee666decd, service poc-ids-token-ex-apim.
- Only PATCH existing aiflux-dev-unified;rev=2, API version 2024-05-01.
  Exact UTF-8 bytes: `{"properties":{"isOnline":false}}`.
  If-Match is the actual opaque ETag from the fresh revision2 GET; no wildcard.
- Reservation nonce a74c955500c9c14b4c8ffe6e9b1da913; original source digest
  9c678b621b3ae289d7ca9906560a3ee59b0dcacd24b1661391cd3b03b78246c1.
- Existing Terraform owner remains desired offline. Local state lineage
  8b19b704-7224-db80-7600-ef2a0cbeef10, serial 185, exact retained hash is checked.
  Never import, copy, push, refresh-write, replace or rewrite state. Reconciliation
  is read-only comparison of actual ARM state against the same owner's desired
  false value. No claim of Terraform validation/execution for this correction.
- The only current-versus-original creation source delta is the retained
  default-off Terraform correction in the staging configuration. The guard
  requires its bytes to match correction02's retained source manifest, while
  every other original source remains exact. The new review manifest binds
  these current bytes separately; the original source digest is historical,
  not falsely presented as the current correction source digest.
- Actual retained AzAPI state encodes the request body as a dynamic object with
  `type` and `value` fields. The guard decodes this representation read-only and
  requires its value to equal the exact owned revision creation body, including
  boolean false online/current flags. It does not confuse the wrapper with an
  online flag change, nor rewrite it to pass comparison.

## Parent review contract

The offline `prepare-review` action takes an actual successful JUnit fixture
report and creates an exclusive manifest in the original evidence folder's
arm-offline-correction01 child. The manifest binds the new source, tests, this
handoff, all deployment Python helper sources, original bound Terraform sources,
original receipt/nonce/baselines and local state identity. The report's hash is
bound separately. The manifest is NOT an independent review receipt.

Only after reviewing those exact bytes, the parent retains its actual native
review transcript inside that child and creates a parent-review JSON record
with the fields `approved: true`, `independent_native_review: true`,
`manifest_sha256`, timezone-aware `at_utc`, relative `transcript` and
`transcript_sha256`. Approval must be younger than 30 minutes at execution.
These are parent attestations backed by retained transcript bytes, not a
cryptographic assertion of reviewer identity and not proof supplied by fixtures.
Do not fabricate that record, reuse the old creation review or manufacture a
new Terraform plan. Source changes require a newly bound package/review.

## Execution contract (parent only after native review)

The separate `execute-reviewed-once` action validates the exact review and
sources, then uses the existing runtime CLI helper internally for ordinary ARM
authentication and account context; tokens are never printed or written.
The existing read helper is used only for protected metadata reads, including
documented appsettings/list reads. Provider retry behavior is not used for PATCH.

Immediately before the PATCH it freshly compares all13 protected components
and supplemental role/RAI/network metadata to the original baseline, the whole
flat revision list to the retained revision1/revision2 baseline, exact ownership
description/nonce, current revision1 metadata, local state bytes/lineage/serial,
remote state HEAD, competing workers and historical intent hashes. Only the
owned noncurrent online revision2 may be corrected. Missing ETag, pagination,
baseline drift, an existing intent or mismatched ownership stops before write.
Historical retained evidence alone is not represented as a live check.

An exclusive global ARM take-offline intent is flushed and fsynced before
starting the request process. That intent is never deleted, including on a
crash, failure or ambiguous timeout. Exactly one urllib open uses PATCH, the
constant URI/body and actual If-Match; default verified TLS uses the existing
corporate CA trust. No HTTP redirect handler follows any redirect, no SDK retry
pipeline, no automatic policy-token replay and no async-operation polling exists.
Socket timeout is 60 seconds; a separate spawned process has a parent 60-second
response watchdog and is terminated on timeout. Process cleanup can take up to
two additional five-second joins; timeout is always unknown outcome/no retry.
Token transfer to the child is in local process memory, not command arguments,
environment overrides or evidence files. No portal credential collection.

Success requires fresh flat `isOnline=false`, `isCurrent=false` for revision2,
unchanged entire current revision1 response and all13/supplemental equality,
unchanged local state/source hashes and remote HEAD. HTTP success alone is not
success: a 202 is not polled, and an unchanged online flag is a stop, not a retry.
HTTP error status, allowlisted ARM error code and request ID are retained without
raw body/message/token. HTTP/transport failure stops without retry; actual
read-only follow-up for an ambiguous outcome is a parent reconciliation task,
never permission to repeat the PATCH. After-read failures retain observed
protected and flat-list evidence before asserting the flag.

## Review checklist

- Confirm actual fixture report count/hash; fixtures are not cloud acceptance.
- Confirm no execution/parent-review receipt was created by the preparer.
- Inspect the no-redirect handler and single opener call, conditional request,
  watchdog, durable exclusive intent and fresh pre/post guards.
- Review read helper dependencies and their token/TLS/metadata handling.
- Verify exact state owner/body shape against retained local state offline.
- Understand `isOnline` is annotated read-only in Swagger; the service may reject
  or ignore this request. Neither annotation nor fixtures establish acceptance.
- No changes to original correction02 artifacts; never replay their saved plans.
- Applied guidance: verified TLS, bounded responses/timeouts, least write scope,
  no credential logging, source-bound review, diagnostics and focused tests.
  Region/quota/naming/new-resource/RBAC deployment rules do not apply: there is
  no resource provisioning, SKU change, IaC deployment or RBAC write here.

The final preparer response supplies actual source/manifest/test-report hashes.
Live ETag, fresh baseline and service acceptance remain deliberately unclaimed
until the reviewed parent execution actually performs the fresh checks.