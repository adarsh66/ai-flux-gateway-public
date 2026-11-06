# Internal and organization-specific external pricing — source implementation

## Status

Implemented in source on 2026-11-02. **Not deployed. No production database,
prices, gateway policies, images or Terraform state were changed.**

## Behavior

- The existing `rate-card` configuration remains the common internal cost card.
  Its Save hook and Auto pricing publication continue unchanged.
- Separate external price-card heads/revisions store a common baseline and
  organization overrides using full organization IDs and optimistic concurrency.
- External updates are explicit `set`, `unknown` or `inherit` operations.
  Inheritance follows the external baseline at the usage event time, never the
  current internal card. Zero is a price; unknown is not free.
- Decision-1 remains scoring-only with an input-only tariff.
- Historical external estimates use half-open effective periods. Recorded costs,
  financial pricing rows and budget enforcement calculations are not rewritten.
- Customer JSON and CSV use external estimates. Recorded internal costs and
  internal-cost-derived balance signals are excluded; administrators retain them.
- Legacy customer routing explanations are price-free, including test fallback
  replies. The browser's direct gateway request path is unchanged.
- Admin pricing has Internal costs / External prices tabs, an external default
  selector and organization selector, draft discard protection, version conflicts,
  and explicit unknown/reset operations. Auto status polling is internal-only.

## APIs

| Resource | Method | Purpose |
| --- | --- | --- |
| `/api/admin/rate-card` | GET / PUT | Existing internal card |
| `/api/admin/external-rate-card` | GET / PUT | External baseline |
| `/api/admin/organizations/{organization_id}/external-rate-card` | GET / PUT | Organization overrides |
| `/api/rate-card` | GET | Authenticated customer's effective external prices |

Customer organization is derived from the authenticated principal, not a query
parameter. External saves never call the Auto publisher.

## Migration and initialization

The additive `0004_external_pricing` migration merges the two formerly duplicate
0003 branches after giving the portal-users branch a distinct identity. It
creates external head/revision tables without populating prices. Offline migration
tests cover fresh and historical branch-stamped databases; production migration
history still requires inspection before release.

`aiflux.external_pricing_migration` is an explicit operator CLI with
`--init-baseline` and `--actor-object-id`. It freezes bundled defaults, scoring
tariffs and existing published internal rate history in one idempotent operation.
It records source version/hashes and serializes against the internal pricing
head. It does not expose supplier provenance to customer APIs.

Run the schema migration and baseline initialization as controlled release steps,
**not** in customer GET handlers, organization creation, inference, or application
startup. No per-organization initialization is required. Until initialized,
customer monetary values are unknown and inference remains unaffected. External
admin writes report that initialization is missing instead of overwriting history.

## Verification completed

- Combined focused Python suite: **204 passed, zero failures/errors/skips**.
  Receipt: `.deployment/feature1-pricing-source-20261102/verified.xml`.
- TypeScript checks: shared UI, admin portal and customer portal each exit 0.
- Editor diagnostics: no errors in checked implementation files.
- Tests include customer ownership/privacy, internal-price independence, scorer
  semantics, unknown/zero, effective history/reset, version conflicts, baseline
  idempotency, actual SQLite Alembic upgrades, and existing Auto publication.

## Outstanding release validation

- Frontend tests are added/updated but **not executed**: local esbuild/Vitest are
  blocked by machine policy. Use the approved Linux validation environment.
- PostgreSQL multi-session concurrency, deployment-specific schema permissions,
  mixed-version rollout, and authenticated served-asset checks are not verified.
- No live browser verification or paid inference calls were performed.
- No whole-repository test pass is claimed; the workspace contains pre-existing
  changes outside this feature.
- Customer-facing Auto metadata still includes internal pricing revision/hash
  fingerprints (not monetary amounts). A separate narrow gateway review is needed
  if these fingerprints must also become private; no policy edits were made here.

Do not roll back to an older customer API that discloses internal costs. Preserve
external revisions and prefer a forward fix. Coordinate customer/admin assets and
API contracts before enabling the release. Models, quotas, safety, Auto pools,
generation settings and the live 1024-token output allowance are out of scope.