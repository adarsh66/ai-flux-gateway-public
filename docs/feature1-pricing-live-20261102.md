# Feature1 pricing — live verification, 2026-11-02

**Deployed and migrated once; authenticated browser/API, immutable assets and fresh
full protected Azure postguards verified.** No new deployment or migration required.

Authoritative [final report](../.deployment/feature1-pricing-live-20261102-01/FINAL37.md)
and [machine receipt](../.deployment/feature1-pricing-live-20261102-01/FINAL37.json).

Current root/child state: **146/203**. Production API/admin/customer digest prefixes:
**8d4f6f5f4ff7 / 6f224ce9f315 / c46bb50fd3a9**. Full digests and evidence are in the report.

Admin internal/default/org pricing and customer effective pricing are authenticated
200, USD, 23 models including input-only Decision-1. Caldova inherits the frozen
external default; all visible prices match the unchanged baseline. Customer JSON
and usage/scoring CSV checks omit internal costs and provenance; customer admin-card
GETs are denied403. Admin internal showback remains available.

Customer Playground retains **22 chat models + Auto**, three routing profiles and
the **1024-token** cap. No paid inference or key reveal was performed. Both portals'
served HTML/JS/CSS exactly match immutable production image bytes. All five temporary
resources are actual404; PostgreSQL public access Disabled. Temporary schema deletion
uses the original operator receipt, not a recreated runner or fresh database query.

Retained tests, not rerun: **208 Linux API + 61 frontend**, customer validation success,
and real private PostgreSQL migration/concurrency tests. Fresh full protected guards
preserve settings, roles, networking, APIM, gateway, ingestion, all22 and Auto1024.

Initial external404s and one usage504 resolved on subsequent authenticated GETs
without intervention; causes are not proven. Optional admin Auto-config GET remains
404 in the sealed app, while customer Auto availability/Playground work. Raw private
API /health and /ready were not independently reached; portal health and authenticated
usage health passed. These limits are retained rather than hidden.

Historical build receipts' `deployed:false` are build-stage metadata. Original
apply postguardfalse was resolved by exact duplicate ARM image-field proof, not a
second apply. FINAL37 supersedes the older browser-pending status without rewriting
historical receipts. **Do not build/apply/migrate/init or resubmit validations again.**