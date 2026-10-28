# Runtime image release — 2026-10-23

## Actual implementation and publication

Release: `local-20261023t074801z-939ccecd80d1`. All five runtime images were
built from 104 allowlisted current-local-source files using Terraform-controlled
ACR actions against the existing registry. Every run succeeded and each digest
was independently read from ACR. No runtime resource/configuration/RBAC writes
were made. This is a published release, **not a deployed PostgreSQL application**.

All repositories below are under `pocidstokenexacr.azurecr.io`:

| Repository | ACR run | Verified digest |
| --- | --- | --- |
| aiflux-api | cmn | sha256:464faf959440e9ef320b326fa6fe10fb2ac0fec58445c152120eb6dd28d1b752 |
| aiflux-admin | cmj | sha256:70b09f66387c98b91f9402d84e6b665bfb342592864a753844b352397df836f5 |
| aiflux-customer | cmp | sha256:16f31b4d2885a3141f77ccb72deafdcb09f7a957c20d1e7cafd0001a3bee074c |
| aiflux-ingestion | cmm | sha256:ec958929dcf188929e12cf271200205efd0566447b20b7ab869fc141f1fef555 |
| aiflux-control-plane-function | cmk | sha256:480a5fd345f8648912db242c480da80096209318aaf3cf14ae22378e0a5158a5 |

The [build coordinator](../scripts/build-images.mjs) now includes both Functions,
captures Unicode build logs through the installed Azure CLI runtime without shell
interpolation, and supports read-only verification of a previously scheduled
release. A local CLI cp1252 log-stream failure was repaired; it did not represent
a remote build failure or require rebuilding the successful images.

The [publication adapter](../services/control-plane/functions/handlers.py) and
[worker](../services/control-plane/src/aiflux/publication_worker.py) reuse the real
versioned gateway publisher. Only the current persisted intent is retried, with
the existing conditional ETag, drift checks, remote readback and audit behavior.
Conflicts fail the invocation. It does not invent release/provisioning jobs or
return fake success. Its [Functions image](../services/control-plane/functions.Dockerfile)
uses the Azure Functions Python 3.11 host, installs application dependencies, and
checks real handler/driver imports during build. Its activation is fail-closed.

**Under the current Terraform-only Azure resource/configuration write policy,
publication must remain disabled:** the existing publisher performs APIM
configuration writes through its runtime SDK, not Terraform. Any future activation
needs an explicitly approved runtime-publication policy and fragment-scoped
central permissions for the worker identity; current API grants are not proof
of worker authorization. No such exception/grant is claimed here.

Release/provisioning worker engines do not exist in the source. Their Terraform
feature settings now remain false instead of claiming they are available when
the publication worker is enabled. Ingestion currently uses the existing Azure
Monitor timer implementation; Event Hub connection settings alone do not create
an Event Hub consumer or ledger-sync engine.

The historical [private SQL runner](../infra/sql/private-runner.Dockerfile) is an
optional MSSQL operator artifact, not a PostgreSQL runtime workload. Its source
imports the removed `PortalUser` model and MSSQL-only initialization logic. It was
not misleadingly published as a working PostgreSQL runner. The local all-in-one
development container and external vendor sidecar are not additional application
images required by this deployment.

## Verification performed

- All five remote Docker builds and manifest reads succeeded, including actual
  Linux TypeScript/Vite portal builds and Functions dependency/import checks.
- Focused current-source worker/publication/ingestion suite: **74 passed,
  1 deselected, 1 warning**. An earlier unfiltered run had 74 passed and one failure
  from the known local duplicate migration revision `0003`; it is not concealed.
- [Packaged-runtime verifier](../scripts/verify_packaged_runtime.py): all 104 file
  hashes and Python syntax passed; the exact archived migration graph has unique
  head `0003`; upgrade from an empty disposable SQLite database and repeated
  upgrade both passed. No Azure database was accessed. The incompatible local
  legacy migration is excluded from the archive, not deleted/renamed/stamped.
- Terraform build-root and platform-root validation passed with the retained
  trusted-provider override warnings. Windows-native test filters ran the actual
  local-login/rebuild suites: **6 passed, 0 failed**. An initial forward-slash
  filter discovered zero tests and was corrected, not counted as success.
- Editor checks on changed implementation files reported no errors.
- Release JavaScript syntax checks and changed Terraform formatting checks passed.
  Repository-wide diff whitespace checking found an existing extra EOF blank line
  in the user-edited disabled test; that unrelated edit was preserved.
- Portal dependency installation reported 4 audit findings (1 moderate, 1 high,
  2 critical). No forced dependency upgrade was mixed into this deployment.

## Runtime rollout attempted, correctly blocked

The [read-only readiness verifier](../scripts/verify-runtime-release.mjs) generated
digest-pinned Terraform image inputs, with all workers disabled,
`manual_rbac_verified=false`, and legacy MSSQL retained. The generated pins and
non-secret readback evidence are in the ignored release evidence directory.

At **2026-10-23T07:57:54Z**:

- All **11** previously requested central grants were still absent from visible
  direct/inherited assignments. See [exact handoff](application-deployment-20261023.md).
- Vault metadata-only read still failed `ForbiddenByRbac`; no secret values were
  requested, logged or copied. Production local-auth secret references remain
  unprovisioned/unverified; no references were invented.
- PostgreSQL is Ready, public access Disabled. This workstation resolves its
  hostname to public `4.193.98.244`, not the private subnet. No existing VM, ACI
  or Container Apps job private-runner candidate was found in the resource group.
  No public database connection or firewall widening was attempted.
- Existing three sites report ARM state Running on their **older** image digests.
  This is not proof of the new release or functional health.
- API public access remains Disabled. Admin retains sole
  `167.103.66.114/32` ingress, default Deny. Customer remains public, with SCM
  separately default Deny. Every site has zero SCM allow rules.

A fresh Terraform platform plan using the actual published image pins was run.
It failed on the intended safety checks: production local authentication has
`local_auth=null`, and central-team grant verification remains false. **No runtime
apply was performed**, and the failed partial plan must not be applied. No gate
was bypassed and no historical local state snapshot was used.

## Exact remaining work

1. Central administrators supply/verify the narrow grants and approved secret
   provisioning; keep the RBAC attestation false until evidence supports it.
2. Supply an approved private execution route and bootstrap PostgreSQL with its
   authorized administrator; verify real runtime MI DML/no-DDL permissions.
3. Supply reviewed vault references, then generate/review a fresh non-destructive
   Terraform runtime plan, preserving legacy SQL, private data/API and closed SCM.
4. Apply through Terraform only; verify image activation, health/readiness,
   login/invalid-password, customer/admin authorization and real gateway acceptance.
5. Keep absent release/provisioning/Event Hub/ledger-sync engines explicitly
   unavailable; image publication does not implement those capabilities.

No final-running PostgreSQL application, live bootstrap, worker execution or
new-release E2E success is claimed.