# Customer Send lifecycle release preparation — 2026-10-29

Scope: customer image only. **Not Auto enablement, not Validated, not deployed.**
The global/current/owned revision policies and their incompatible path predicates
are untouched. No diagnostic attempt is renewed or replayed.

## Source and compatibility review

Reuse cm37, not another validation build: 160 UI tests, 17 files, three TypeScript
checks, two portal builds, no published image. Retained source digest:
18341f9ac56523fdd1af41dab2b0bcbff653657abf4d5165b98162e795268a48.
The new controller recomputes all77 workspace/context hashes, all4 launchers,
the log and result, then copies only the existing customer Dockerfile COPY inputs.
No control-plane, ingestion, infrastructure, admin application source or validator
Dockerfile is uploaded in the customer production context. Shared UI includes
Auto code; this is explicitly **not a four-file-only production byte delta**.
The package records every changed source vs the deployed customer login source
and a complete diff. The four latest lifecycle repair files are part of that
larger already-validated shared UI source.

- [Playground](../packages/ui/src/pages/PlaygroundPage.tsx) obtains availability
  independently of models/subscriptions. Only `auto.data?.ready === true` adds
  Auto. Missing, rejected, pending or failed availability cannot hide explicit
  models. The deployed API has no Auto implementation; a missing availability
  endpoint is an expected compatibility case, not an instruction to ship API code.
- [Client](../packages/ui/src/client.ts) adds only an optional local AbortSignal
  to the existing reveal request; URL, POST method and JSON key body stay the same.
  The Send path retains the existing direct gateway request and explicit alias.
- [Lifecycle guards](../packages/ui/src/pages/PlaygroundPage.tsx) own the entire
  reveal-to-Send operation, reject duplicate actions, bound credential retrieval,
  cancel on reset/scope/unmount, discard late credentials/results and never retry.
- [Retained tests](../packages/ui/src/auto-routing.test.tsx) cover pending/failed
  readiness retaining explicit models; this is not fresh actual-page/404 proof.
  [Lifecycle tests](../packages/ui/src/token-exchange.test.tsx) and
  [client tests](../packages/ui/src/client.test.ts) are part of cm37, not rerun here.
- The customer entrypoint does not mount the new admin router page. Admin remains
  on its existing immutable image. Auto settings, publication receipts, profile
  initialization, migrations, model deployments and telemetry are not changed.

## Preparation and review contract

[Controller](../scripts/deployment/customer_send_release.py) exposes only
`prepare`, `check`, `build`, `plan`. There is **no apply entrypoint**.

`prepare` does account/GET-only metadata reads, state blob HEAD, full four settings
hashes via the existing documented read API, full13 protected baseline and
supplemental role-definition/RAI/network comparison to the retained original
baseline. It requires local state185 exact bytes/lineage, exactly revisions1/2
with explicit online/current flags, current1 full metadata unchanged, all4 exact
image predecessors and the existing state-storage167.103.66.248 rule/defaultDeny.
It never adds an ACL, acquires a state lease or invokes Terraform/build/push.
It performs a second full13 snapshot before declaring preparation successful.

Predecessors on existing registry pocidstokenexacr.azurecr.io:

| Component | Required immutable SHA256 |
| --- | --- |
| Customer | a30d513ce0dd7c529491689a49ce311f7794f4785e1dd5c5577ae62da9f1b975 |
| API, unchanged | 29b67faa7bdeeb1a6ceadcee084a559d7023521bdd79959cec52c8bb34c78c64 |
| Admin, unchanged | 2846f1ff04244f20cb6612cca62c348b6a79a2fff7245dfc609347564becbfe5 |
| Ingestion, unchanged | fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90 |

Parent must perform an actual independent source/package review, then supply
parent-build-review.json **inside the new package**; it is deliberately not
generated or self-approved. Required fields: scope
`CUSTOMER_SEND_IMAGE_BUILD_ONLY`, decision `PASS`, actual_independent_review true,
exact package_sha256, actual reviewer_pid distinct from the executing process,
actual UTC review time, summary_file and summary_sha256. The actual nonempty
review summary is bound to the package; the controller cannot authenticate the
truth of a manually supplied review, so parent owns that provenance.

Only after that review, the package's next_parent_reviewed_build_argv submits
one native Linux/amd64 production customer build on the existing registry, using
the retained customer Dockerfile, local auth, existing /api proxy and exact
normal gateway URL. This future operation publishes one immutable customer image;
it is not performed by preparation. Exclusive fsynced intent precedes submission.
Failure, timeout or unknown outcome consumes it: reconcile the actual run, never
retry. Review/source/context/tooling/predecessors/full baseline are rechecked.

## Future plan, not an existing saved plan

There is deliberately no invented image digest or placeholder saved plan.
After a genuine build, `plan` verifies its remote ACR run/output/tag/digest, copies
the existing Terraform root into the isolated package and preserves all current
settings using the existing registry-field normalization and literal escaping.
It creates one exact customer target plus identical-input full companion. The
target must have exactly one in-place existing customer image update; all other
settings/identity/network/site fields remain equal and no writable unknown is
accepted. API/admin/ingestion updates, creates, deletes, Auto flags and any other
write fail the guard. The complete companion is **NEVER APPLY**, even if it has
unrelated existing dirty-workspace changes. Actual independent exact-plan review,
the existing azure-validate workflow/Section7, fresh saved-plan/state/source
binding and a separately reviewed apply-once executor are still mandatory.

Parent's next action is source review, not another diagnostic/global-policy
experiment. Customer release acceptance must use a reviewed no-cloud actual-page
fixture first; synthetic results never prove scoring. A later real bounded
explicit Send requires its own recorded budget and must not silently become an
Auto attempt. Live Auto remains blocked as documented in
[path admission research](auto-live-release-preparation-20261029.md).

## Execution evidence

Preparation and offline-test results will be reported in a separate unbound
handoff so this source-bound review document does not change after preparation.
No independent review or production validation is claimed by this document.