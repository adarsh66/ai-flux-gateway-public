# Customer cm38 image-only saved-plan preflight — 2026-10-29

Scope: prepare one fresh exact target and an identical-input **NEVER APPLY**
companion. **No apply, new build, Auto enablement, settings publication, policy,
revision, authentication, role, identity, network or database write.**

## Immutable build provenance

The existing production customer build is cm38, not a new cm37 validation run.
Its source-bound package remains
[original build package](../.deployment/customer-send-20261029T105702534025Z/package.json),
SHA256 d300b722a3b53df753af998625edc9ff88cf5da6f1432e173d3d82c7666922b8.
Actual output:
pocidstokenexacr.azurecr.io/aiflux-customer@sha256:5f55df7d5fbc094f37011906c503e96b8c01e329978d6bca9ac9a7d8318eb589.
The existing immutable customer predecessor is
a30d513ce0dd7c529491689a49ce311f7794f4785e1dd5c5577ae62da9f1b975.

The [source-bound controller](../scripts/deployment/customer_send_release.py),
its tests, original documentation, contexts, build intents and receipts are
unchanged. A thin [successor adapter](../.deployment/customer-send-plan-once.py)
reuses the existing exact build verifier, settings normalizer, Terraform
environment, companion resolver and image-only guards, without invoking any
historical workflow entrypoint. All176 original tooling hashes were separately
checked unchanged at11:16:58UTC. New guard tests live in
[successor tests](../tests/unit/test_customer_send_plan.py).

## New package and safety gates

[New package](../.deployment/customer-send-plan-20261029T111900000000Z/intent.json)
was exclusively claimed at11:15:06UTC by process20252. The package-name timestamp
is an identifier, not an assertion of the actual start time; receipts record
actual UTC times. The original process must be reconciled, never resubmitted.

- Fresh full13 and supplemental capture, exact four current settings sets and
  image pins; current1 unchanged and owned revision2 offline/noncurrent.
- Current project-route state185 bytes and lineage are preserved independently
  of the main runtime remote-backend state's own serial and lineage. Do not
  confuse the two state owners or migrate/write either state.
- Existing storage access must return200/unlocked with its existing ACLs.
  No IP rule is added or changed. Full current settings are read through the
  existing documented appsettings/list read operation, not a settings overwrite.
- Read-only lockfile init, validate, default workspace, state list/pull and exact
  customer resource ID/predecessor/settings inspection precede planning.
- Each of the target and companion is generated at most once in this package.
  Both are parsed; exact inputs/configuration and customer change must match.
  All full-plan checks pass before resolving targeted unknown check results.
  Every target write other than the one customer in-place image update fails.
  All writable unknowns fail; unchanged provider-computed outputs use the
  existing finite allowlist. Both archives bind exact configuration/lock/state.
- Actual customer Web permission coverage, customer denies and existing MI
  AcrPull are checked separately from inherited policy/MFA inspection. These
  are static metadata checks, not ARM write probes or deployment acceptance.
- Full after capture must equal before, including remote state headers and all
  protected settings, pins, security, revisions and state185.

## Validation status

Initial offline run: **60 passed**, one existing dependency deprecation warning;
no Azure, Terraform, build or inference performed by those tests.

The actual one-shot preparation/preflight is in progress. This document does not
claim a saved-plan hash, successful Azure preflight, independent reviewer result,
Validated status or deployment before durable evidence exists. Actual official
workflow/Section7 proof will be recorded only for operations actually completed.
Independent exact-plan review remains a later mandatory gate. No apply entrypoint
is exposed by the successor adapter.