# Customer monthly-budget overview — deployed, authenticated acceptance pending

2026-11-04. Live URL: https://poc-ids-token-ex-customer.azurewebsites.net/overview

## Result

The original saved Terraform binary was applied **exactly once**, native exit 0.
Only the customer image changed. Root state advanced **158 → 159**; child state
stayed **206**. Full protected pre/post/final captures and recursive root-state
comparison passed. API, admin, ingestion, settings, roles, identities, network,
APIM policies, all 22 models, output4096, pricing and quotas were preserved.
Feature2 remains paused. Zero paid inference or allocation writes.

Customer image SHA256:
619fe44abdcb782e62b7376483311e4ea978debdc601ee42b6df9fab540b497a

Original binary SHA256:
c8fda1efc7399eb28c3b11f30ab10daed4f76059f19e12580a3bc108bee1e975

## Missing-only recovery and validation

The stopped review called its inherited evaluator with the wrong `feature1`
filename stem. A separately named continuation supplied `customer`, binding both
the existing binary and inputs; it did not rename/copy/replan the binary or weaken
checks. All 38 actual console conditions passed; saved unknown statuses remained
unknown. Archived modules/lock/root matched, all six unsafe-plan mutations were
rejected, and existing customer UAMI AcrPull was verified without a grant.

The actual official validation workflow completed all nine steps through
UpdateStatus with populated proof. Original successful native validate/fmt/plan/
show evidence and sealed **cm6t 74/74 tests** plus **cm6u** production were reused;
no builds, plans, or other consumed operations were replayed.

The first apply wrapper stopped **before Terraform submission**, on a still-present
external Python process. The fresh successor used finite supported waits followed
by a new unchanged full worker check; no exemption, kill or waiver. Only the
successor invoked Terraform apply. Inventory found zero new resources.

## Live verification and remaining blocker

Actual nginx document-root HTML and both directly referenced JS/CSS assets each
returned HTTP200 and matched the new immutable image byte-for-byte, all from its
new production COPY layer. Manifest/layer digests, effective public Vite config,
monthly endpoint, vertical gauge and monthly USD allocation markers passed.
Final full protected capture retained root159/child206, exactly matching postapply.

The normal existing customer browser session rendered the new shell and monthly
refresh control, but data requests returned401 and the page displayed **Invalid
access token**. Consequently, live authenticated gauge/allocation values are
**not accepted**. A normal user sign-in is needed for read-only acceptance; the
token failure cause was not diagnosed. No credential extraction or auth bypass.
No additional build, plan, apply or rollback is needed for this browser check.

## Evidence

- [Missing-only review](../.deployment/customer-budget-overview-20261104-01/REVIEW07.json)
- [Exact saved-plan review](../.deployment/customer-budget-overview-20261104-01/rollout06/REVIEW06.json)
- [Official completion](../.deployment/customer-budget-overview-20261104-01/official08-UpdateStatus.json)
- [Single apply](../.deployment/customer-budget-overview-20261104-01/rollout06/APPLIED06.json)
- [Live state proof](../.deployment/customer-budget-overview-20261104-01/rollout06/LIVE06.json)
- [Immutable served assets](../.deployment/customer-budget-overview-20261104-01/verification11/customer-image-proof.json)
- [Final protected guards](../.deployment/customer-budget-overview-20261104-01/verification11/GUARDS.json)
- [Browser blocker](../.deployment/customer-budget-overview-20261104-01/verification11/BROWSER12.json)

Do not replay consumed controllers, builds, predicates, official steps, saved
binary apply or verification captures. All original failure receipts remain.