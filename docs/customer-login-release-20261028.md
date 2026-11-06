# Customer login CTA removal release — 2026-10-28

## Authorization and scope

The user explicitly authorized a fresh existing-setup customer-only production
release. No onboarding, azd adoption, new infrastructure, role/network/key/DB
operation, inference, publisher retry, settings save or policy activation is used.
Only the existing customer site's immutable container image may change.

Fresh evidence directory: .deployment/customer-login-20261028T124500Z.
Audited companion-only successor: .deployment/customer-login-20261028T125500Z.
Historical customer, Showback and POC artifacts are retained and not replayed.
No active Python/Terraform workers were observed before preparation; local durable
intent reconciliation is recorded in that directory. The long-lived Azure MCP
server is not a deployment worker. An initial preparation attempt stopped before
any release directory/intent because optional psutil was absent; the fresh script
was corrected to native Windows process metadata. Its 13 guard tests then passed.

## Source and native validation

The existing minimal edit in [auth.tsx](../packages/ui/src/auth.tsx) removes the
signed-out registration CTA, retaining default login mode and the unreachable
registration branches. Backend registration stays unchanged because no API image
or backend source is packaged or deployed. Shared admin auth source changes exist
locally, but the live admin image is deliberately not changed by this release.

The complete 74-entry manifest and staged context were rehashed and remotely
checked against retained no-push `cm2x`, successful at
2026-10-28T12:19:29.600474+00:00 with no image outputs. It passed 124 UI tests in
16 files, three workspace typechecks and both ephemeral portal production builds.
Source SHA256: `91443fba5fe909624fde27f1b0e6a54783fe74a8536acf0698c02231604921c4`.
No validation tests or no-push build were replayed.

The deployed customer predecessor is
`sha256:d9d8b4b21283801feb2aff3ad12707155f5c38c59b6fc09091a4c22c35e71ea3`.
The source delta against that customer's retained manifest is recorded in
scope-review.json and bundle-scope.diff within the fresh evidence directory.
It includes prior shared-UI Showback/client/types/usage edits and their tests;
this is **not** claimed to be only a CTA byte delta. Customer routes and backend
access authorization remain unchanged. Current regression coverage includes
customer/admin login, customer usage, pagination and model contracts.

## Production build

Exactly one source-bound curated Linux/amd64 production customer build/push:
`cm2y`, successful at 2026-10-28T12:37:30.369806+00:00.
Tag: `customer-login-20261028t124500z-91443fba5fe9`.
Image:
`pocidstokenexacr.azurecr.io/aiflux-customer@sha256:a30d513ce0dd7c529491689a49ce311f7794f4785e1dd5c5577ae62da9f1b975`.
Exact one registry/repository/tag/digest output and production nginx validation
were verified. No API/admin/ingestion build or push occurred.

Existing dependency audit findings (1 moderate, 1 high, 2 critical), Vite chunk
warnings and one local Starlette/AnyIO deprecation warning remain disclosed.
No dependencies were upgraded and no clean vulnerability-scan claim is made.

## Protection and validation gate

Fresh live preflight matched all expected immutable pins. Baseline SHA256:
`5a3b3bb12ca4597b0fec89ae9c3caf42ed184209e6bef04c7c682adabfd9772f`.
It captures all four complete settings hashes, API/admin/ingestion images,
APIM product/auth/routes/policy/counters/safety, current detached fragment content
and metadata, 13-model metadata and RAI bindings, RBAC, private PostgreSQL,
network/state ACL, ingestion timer/AlwaysOn/cutoff and active product metadata.
The current fragment has an extra self-harm0 branch; no historical revision8
default assertion, settings restoration or publication is made.

The exact saved plan may update only one existing customer's image. Any excluded
unknown check must resolve through a full identical-input NEVER APPLY companion;
its broader writes are never approved. The independent validator executes actual
strict mutation tests, Terraform fmt/validate/default workspace/state ownership,
remote source/build provenance, existing operator/AcrPull role definitions,
subscription policy metadata, final complete baseline equality and the installed
official Git Bash azure-validate workflow sequentially. Actual Section 7 proof
and workflow completion are required before one exclusive saved-plan apply.

## Current execution checkpoint

Production build completed. The saved customer target was created once, SHA256
`94e471ad205e2eeea17c27489f350c22d1e3f18c3ab619e966968837c2140f2e`.
Its first full NEVER APPLY companion failed reading existing App Service storage
and sticky-setting metadata. No deployment validation or apply occurred.
The Azure troubleshooting guide was consulted; this is not asserted to be an
RBAC denial or an established transient root cause. No permissions/TLS/network
settings were changed as a workaround.

A fresh audited companion-only successor preserves the exact original customer
target bytes, build, source, tooling, settings and baseline. Only a new full
identical-input NEVER APPLY companion is submitted with serial provider reads.
The errored companion and original target remain untouched; neither image build
nor customer target planning is replayed. Independent validation remains required.

The successor companion completed with its strict guard at
2026-10-28T12:58:09.295739+00:00. Exact expanded variables/configuration and
customer target change match the original target; every companion check passes.
Its unapproved noncustomer changes are listed in review.json and never applied.
The separate validator's actual JUnit result is **65 passed**, zero failures,
errors or skips, covering the new customer mutation guard, portal guard and
13-model Fireworks/POC compatibility suites. Official workflow/role checks and
the final independent baseline must finish before Section 7/Validated/apply.

Supplemental read-only evidence at 2026-10-28T12:47:36.069351+00:00 captures all
three actual Foundry RAI policy definitions, 13 deployment bindings, all 31 assigned
role definitions and VNets/NSGs/private endpoints/route tables. Only canonical
hashes/counts are stored or printed. This supplements rather than weakens the
original protected baseline, and must compare identically after apply.

After apply, a separate process must compare the complete captured baseline
allowing only the exact customer image, and check HTTP200/new JS bundle with
login present and CTA absent. The parent owns isolated signed-out browser
verification; shared authenticated browser sessions must not be signed out or
their storage/tokens inspected. Do not retry apply after any wrapper failure.