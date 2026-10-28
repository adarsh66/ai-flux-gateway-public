# Existing-registry image builds only

The build map now contains all five application runtimes: API, admin, customer,
usage-ingestion Function and control-plane publication Function. The latter is
not the Uvicorn API image. Both workers remain disabled for deployment pending
real runtime authorization and readiness. The publication adapter cannot be
activated under the current Terraform-only configuration-write constraint.
See [verified release evidence](../../docs/runtime-image-release-20261023.md).

This root owns only two ACR action kinds: `listBuildSourceUploadUrl` and
`scheduleRun`. It never manages the registry, applications, runtime settings,
identities, role assignments, database, network or secrets. Existing runtime RBAC
gates in the platform root are unrelated to image publication and remain closed.

The coordinator [scripts/build-images.mjs](../../scripts/build-images.mjs):

1. Confirms the existing account/subscription/registry and disabled registry admin.
2. Copies a narrow allowlist of **current local bytes**, including uncommitted
   backend and portal changes, into an isolated source archive. Deployment inputs,
   Terraform state/plans, credentials, environment files, dependencies and output
   bundles cannot enter that allowlist. A SHA-256 manifest records each file.
3. Uses Terraform 1.12.1 and the existing trusted AzAPI 2.13 provider. It initializes
   the existing Entra-authenticated backend with a new release-specific state key;
   it does not load or apply the platform resource graph.
4. Checks each saved plan permits only create actions for the two ACR action kinds
   on the exact existing registry, then applies the saved plan. Upload authorization
   is sensitive; signed upload URLs remain in process memory and protected remote
   Terraform state, never terminal output or evidence logs.
5. Transfers the application source artifact to the ACR-issued blob URL, schedules
   fresh no-cache builds with push enabled through Terraform, reads completion logs
   and confirms each tagged manifest using authenticated registry reads.

Release tags combine UTC build time and the source-manifest hash. No `latest` or
existing release tag is overwritten. Digest references, not tags, are the immutable
publication evidence. No registry tag-lock configuration is changed.

Portal public inputs are `VITE_AUTH_MODE=local`, `VITE_CONTROL_API_URL=/api`, and
`https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1`, matching the current
direct-portal configuration in [apps.tf](../terraform/apps.tf). This records the
compile-time input only, not live gateway route or inference acceptance.

The untracked legacy `0003_portal_users.py` migration is excluded from the archive,
not deleted or renamed locally. It refers to `portal_users`/`PortalUser`; the
current [models](../../services/control-plane/src/aiflux/models.py) define
`LocalUser`, and the tracked
[stable-teams migration](../../services/control-plane/migrations/versions/0003_stable_teams.py)
already creates that table. The packaged migration graph has unique revisions and
valid parents. No existing database history is read, stamped or migrated.

Evidence is written beneath the ignored local deployment directory, under
`image-build/<release-tag>/`: file hashes, archive hash, preflight registry metadata,
Terraform init/validation/plan/apply logs, ACR run records/build logs, verified
manifest metadata and final results. Plans and state may contain short-lived
upload authorization and must not be published or added to source control.

Execution requires the approved corporate CA bundle, authenticated Azure CLI for
read-only/auth operations, the trusted provider configuration and Node. All Azure
resource actions remain Terraform-controlled. The API container starts Uvicorn;
building it does not execute bootstrap or migrations.