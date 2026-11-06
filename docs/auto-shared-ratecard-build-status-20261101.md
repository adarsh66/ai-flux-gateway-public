# Shared rate-card build-only status — 2026-11-01

## Scoped admin continuation05/06 — supersedes the historical approval blocker

The user explicitly authorized honest clean878 scoped validation, not unrelated
production changes to reproduce historical cm4k test names. No further approval
gate is required for this admin-only build. Historical sections below are retained
as the earlier assessment, **not the current acceptance requirement**.

The separate exact-source auditor verified all 57 production/context source files:
only `packages/ui/src/pages/RateCardEditor.tsx` and `packages/ui/src/types.ts`
differ from the production878 composition. Removing the additive informational
status component and optional typed metadata exactly restores the previous source
(newline-normalized structural comparison; raw-byte bindings retained). Save and
rate-validation code are unchanged. Thirteen differing dirty-workspace runtime
files are explicitly **not shipped**, including auth, chat, client, Playground,
router, navigation, charts, and styles. No historical runtime substitutes are used.

### Actual first scoped run: cm50 (failed; immutable)

| Stage | Actual result |
| --- | --- |
| Rate-card focused suite | 27 passed, 0 failed |
| Explicit new Saved/Applied subset | 10 passed, 0 failed; 17 intentionally unselected |
| Components + DisplayPrice | 28 passed, 0 failed |
| All 20 composed compatible test files | 194 passed, 1 failed; 195 total |
| Typechecks / portal builds / image | Not reached; no image |

The sole broader-suite failure was an asynchronous test/source mismatch:
showback selected `model-b` after waiting for the Model dropdown to be enabled,
but clean878 keeps that dropdown enabled while discovery is pending. A new
successor adds only a wait for the actual option before selection. Every original
loading/error/retry/empty/stale-response assertion remains intact. There is **no
production regression fix or unrelated feature delta**.

Successor06 has a distinct exclusive intent and tag. Its production files are
byte-identical to cm50; only the showback test synchronization line differs.
**Original cm51 succeeded at 08:06:45 UTC**, with the following actual results:

| Stage | Actual result |
| --- | --- |
| All composed clean878-compatible tests | **195 passed, 0 failed, 0 skipped; 20 files** |
| Focused rate-card suite | **27 passed, 0 failed** |
| Explicit new Saved/Applied subset | **10 passed, 0 failed; 17 unselected** |
| Components + DisplayPrice | **21 + 7 = 28 passed, 0 failed** |
| Production TypeScript checks | **3 passed** (shared UI, admin, customer) |
| Portal production builds | **2 passed** (customer validation only; admin packaged) |
| Source hash checks | **57 exact files**, before tests, after test removal, after builds |

These are overlapping executions, not additive distinct-case counts. The 17
unselected cases in the explicit subset also passed in the full 27-case run.

Admin image pin:
`pocidstokenexacr.azurecr.io/aiflux-admin@sha256:11d9b230d9312afe4b945fc8854d1aa7a7fee2ee078b58132a3d98cbe57216eb`.
Unique tag: `shared-ratecard-admin-scoped06-20261101`.
Context SHA256: `f5e65d1041727ee354bcd1802ad5d4ca3eef77777f2b0252308d6bf1978d065f`.
Original raw log SHA256: `d5480ecc53da557ea8b7d9c6a476f3199b14898cae16a1b6ace8131767a66ef3`.
New packaged JS SHA256: `34890858bbdc49155603a23efcd8c5f8fdd79df1347eb27c0871acf26070cf75`.
New packaged HTML SHA256: `4707aa57a0a146cf9e3822f80bf38d2c1cbe69b2e449e311d0ab24ab15f4dbfb`.
Packaged CSS is byte-identical to live878. The new image is **built, not deployed**.

Historical cm4k's 233 passes are not exact-production878 coverage. Its whole
Auto-routing/router-auth files and later Playground credential-lifecycle block
are retained outside the upload; clean878 chat/client assertions replace the
incompatible historical contracts. Components and DisplayPrice assertions kept
in scope are unchanged; scoring/usage HTTP fixtures use their actual unavailable
response contract. All composed compatible tests run, without skip-marking
individual failures. This does **not** claim 243 historical passes.

Current live878 GET-only verification matches the retained built/served assets:
admin JS SHA256 `d9059c14a67dbe7afaa07bbfd47b655115839a9f52807d163b594f0901b26779`,
HTML `eb1e2e1581cec51cac6bd1b358a6c5bf6dcd93dd28aa35f9b1fb1961da6fb61a`,
CSS `b5bae5afc0405aeb3dfdf45344891ef236b3499c006ae63c885d4a8b1f16f322`.

Evidence:
- [Successful cm51 completion and digest](../.deployment/auto-shared-ratecard-20261101-01/admin-scoped06/completed.json)
- [Successful cm51 original cloud logs](../.deployment/auto-shared-ratecard-20261101-01/admin-scoped06/original-logs.stdout.txt)
- [Final source/actual case count/asset audit](../.deployment/auto-shared-ratecard-20261101-01/admin-scoped06/final-exact-source-audit.json)
- [Source audit](../.deployment/auto-shared-ratecard-20261101-01/admin-scoped06/separate-source-audit.json)
- [Single test correction](../.deployment/auto-shared-ratecard-20261101-01/admin-scoped06/test-correction.json)
- [Scope/exclusion reasons](../.deployment/auto-shared-ratecard-20261101-01/admin-scoped06/scope.json)
- [Failed cm50 original logs](../.deployment/auto-shared-ratecard-20261101-01/admin-scoped05/original-logs.stdout.txt)
- [Failed cm50 retained actual outcome](../.deployment/auto-shared-ratecard-20261101-01/admin-scoped05/retained02-original-outcome.json)
- [Verified live878 asset hashes](../.deployment/auto-shared-ratecard-20261101-01/admin-scoped06/live878-assets.json)

Independent-agent capability is unavailable; the separately implemented Node
auditor is honestly labelled, not passed off as an independent agent. This is
not an approval gate. API cm4y remains unchanged. No deployment, paid inference,
live SQL/settings/role/network change or local esbuild execution occurred.

## Historical admin continuation: exact-source review04 (superseded)

The separate read-only parent review verified all 22 cm4k test-file bindings and
all 233 actual retained passing cases against the normalized original log hash.
Nine cm4x test bindings are stale. The current rate-card test addition contains
10 cases, so the correct restored expectation is **243**, not 216.
The new 243-case suite has not executed; these are provenance/source counts.

Restoring fixtures alone cannot satisfy exact production878 acceptance:

- Production Playground lacks Auto availability reads and Routing profile UI.
- Production chat lacks Auto request rejection and actual routing metadata.
- Production client lacks accepted Auto methods.
- Production `AdminModelRouterPage` exports the legacy editor, not the accepted Auto editor.
- Production customer auth still offers registration, which accepted tests forbid.

These are production contract differences, not malformed HTTP mock responses.
Substituting historical validation pages/client/chat/auth and restoring production
before building would leave those assertions validating substitutes. That cannot
be reported as full exact-production regression coverage. No assertions were
weakened and no non-rate-card production files changed.

The new admin submission was therefore **not consumed**. No new admin pin exists
and this release is **not ready for apply**. API cm4y and its successful digest,
context, and 90-test receipt are preserved. No cloud replay or new cloud call was
made during this offline review. Independent subagent capability was unavailable;
the separate parent audit is explicitly identified as such.

Evidence: [parent source review04](../.deployment/auto-shared-ratecard-20261101-01/admin-parent-review04.json).

Continuation requires resolving the incompatible scope: either explicitly permit
the non-rate-card production contract corrections, or accept separately labelled
cm4k compatibility-harness coverage rather than claiming 243 exact878 production
passes. Cloud-build authorization itself is already granted; it is not the blocker.

## Actual results

| Component/stage | Original ACR run | Result |
| --- | --- | --- |
| API sealed01 | cm4u | Failed: 56 passed, 34 setup errors; missing settings-unconfigured test fixture |
| Admin sealed01 | cm4v | Failed TypeScript: missing legacy regression-only helpers |
| API sealed02 | cm4w | Failed: 88 passed, 2 missing imported test-helper failures, 1 migration deselected |
| Admin sealed02 | cm4x | Three workspace TypeScript checks passed; 186 tests passed, 30 failed, 216 total in 22 files (16 passed, 6 failed) |
| API sealed03 | cm4y | Succeeded: 90 passed, zero failures/errors/skips; 1 known migration test excluded by selection |

API production pin: `pocidstokenexacr.azurecr.io/aiflux-api@sha256:787a89911c57b02a199e677d3dd6ad77524a518dc88836af5f1deef1b99fe2dc`.

The API03 controller retained the build02 tag, but used a new exclusive submission intent and new context. The prior build02 API failed without output images. Use the digest, not the mutable tag.

API03 ran on Linux Python 3.11 and verified hashes/imports in both production module mirrors against the f04f base. Only validation fixtures/imported test helpers changed across the API successors; production modules and expected mirror hashes stayed exact.

Admin rate-card tests: all 27 passed, including informational sync status behavior. Admin production build and both portal validation builds did **not** execute because full tests failed. No new admin digest exists.

## Remaining blocker and concrete continuation

Full 233 baseline + 10 new UI acceptance is unmet. Nine test-file hashes differ from the retained cm4k baseline; the composed suite contains 216 tests rather than the required minimum 243. Six failing groups are admin-showback (7), auto-routing (6), components (6), model-tokens (7), sgt-granularity (2), and token-exchange (2).

Some failures are stale mocks (scoring response lacks breakdown); others expose preserved production behavior differing from accepted test expectations (Playground Auto profile/readiness and customer registration). Do not silently weaken assertions, replace production pages with historical validation pages, or claim historical cm4k success validates this composition.

Next: review the nine exact test-binding differences and six original failure groups; compose a NEW admin-only successor against the corrected 878 production context, preserve model-catalog navigation/customer simulator removal/auth/Auto/Playground, isolate regression support, and validate the full required suite before submitting another production build. No replay of consumed sealed01/02/03 submissions, composition stages, or baseline capture.

## Evidence

- [API completion](../.deployment/auto-shared-ratecard-20261101-01/build-only03/api-completed.json)
- [API native JUnit](../.deployment/auto-shared-ratecard-20261101-01/build-only03/cloud-backend-focused.xml)
- [Stage outcome](../.deployment/auto-shared-ratecard-20261101-01/build-only03/stage-outcome.json)
- [Separate source audit and test-binding differences](../.deployment/auto-shared-ratecard-20261101-01/build-only03/independent-source-audit.json)
- [Admin original logs](../.deployment/auto-shared-ratecard-20261101-01/build-only02/admin-original-observation-logs.stdout.txt)
- [Admin original status](../.deployment/auto-shared-ratecard-20261101-01/build-only02/admin-observed-status.json)

The separate direct source auditor passed immutable context, API dual-mirror, protected navigation/auth/Playground, and test-support removal checks. Independent subagent review was unavailable and remains unmet.

No live apply, baseline capture replay, paid inference, settings changes, role/network changes, or live SQL writes were performed. Local esbuild was not run.