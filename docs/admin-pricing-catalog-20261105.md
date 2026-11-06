# Admin pricing/catalog local verification — 2026-11-05

## Status

**Later authorized cloud release checkpoint:** original no-push Linux run cm7y
completed Failed (111focused tests passed,2failed). Full UI and both bundles
were not reached; no rollout. Fresh post-full46 passed and originals preserved.
See the [current release report](admin-pricing-catalog-release-20261105.md).
The local-only results below are historical and do not describe the later
authorized cloud activity.

**Partially verified; not release-complete.** Three post-fix TypeScript projects pass. Runtime tests, production bundles, and browser behavior remain unverified because the normal local Vitest startup cannot spawn esbuild. No cloud fallback was authorized or used.

## Source fixes

- The inspected RateCardEditor had only two tabs despite the new viewer tests expecting three. Added View revisions, preserving the existing CardScope/Editor tree inside a hidden wrapper. Viewing history does not change editor audience or organization; pending saves retain their original scope, and draft/conflict state stays mounted. Existing editor card-switch confirmation remains in place.
- Scoring catalog output/cache/write dimensions now show N/A independently of price loading, absence, or failure. Scoring input remains loading/unavailable/unknown as appropriate; missing prices are not zero.
- Chat catalog cards now display published context metadata rather than always showing Unverified. Preserved garden description metadata in the presentation object, while continuing to render curated customer-safe copy instead of operational diagnostics.
- Added four catalog regression cases: published context and scoring N/A during loading/missing/failed prices. These cases are typechecked, not runtime-proven.
- Reviewed historicalAmount: scoring non-input dimensions are N/A; non-billing primary dimensions are N/A; nullable chat cache/write rates remain unknown; known decimal strings render verbatim without Number coercion.

## Exact validation results

Installed executable: C:/Program Files/nodejs/node.exe, Node v24.13.0. Used installed JavaScript entrypoints directly; no npm command shims or security-policy changes.

| Check | Result | Exit | Evidence |
| --- | --- | --- | --- |
| UI tsc --noEmit | PASS, after all source fixes | 0 | [final compiler receipt](admin-pricing-catalog-types-40812-3.json) |
| Admin tsc --noEmit | PASS, after all source fixes | 0 | [final compiler receipt](admin-pricing-catalog-types-40812-3.json) |
| Customer tsc --noEmit | PASS, after all source fixes | 0 | [final compiler receipt](admin-pricing-catalog-types-40812-3.json) |
| Focused Vitest, eight requested files | Startup failed; zero tests executed, not eight failing files | 1 | [startup receipt](admin-pricing-catalog-focused-10588-1.json) |
| Full UI Vitest | NOT RUN: same blocked startup dependency; no pass/count claimed | — | No runtime receipt |
| Admin Vite production build | NOT RUN: same esbuild startup dependency; no blocked executable retry | — | No build receipt |
| Customer Vite production build | NOT RUN: same esbuild startup dependency; no blocked executable retry | — | No build receipt |
| Browser verification of new implementation | NOT RUN: no verified build/dev server for these changes | — | Unrelated existing fixture server was left untouched |
| Editor diagnostics | No errors reported in eight reviewed source/test files | — | VS Code diagnostics, not runtime tests |

Focused files: rate-card, external-rate-card, pricing-history, display-pricing, modelPresentation, admin-catalog-route, pricing-revision-viewer, and model-catalog.

The focused attempt occurred after the catalog fixes but before the missing third-tab integration. It failed before loading tests; rerunning after the tab fix would only repeat the known esbuild startup restriction, so it was not attempted.

Exact startup failure: `Error: spawn UNKNOWN`, `errno: -4094`, `code: UNKNOWN`, `syscall: spawn`, originating at `ensureServiceIsRunning` in installed esbuild while Vite loads the Vitest configuration. This run does not independently identify the policy rule; the workspace has a previously confirmed corporate-policy block on esbuild. No alternate executable, loader workaround, or policy bypass was attempted.

## Receipt reliability and boundaries

Terminal output was truncated after the first compiler, and some terminal commands produced parsing/module-availability failures. The local [validation runner](admin-pricing-catalog-validation-20261105.mjs) records exclusive JSON receipts after each completed child process, including actual status, stdout, stderr, and signal. The final cumulative receipt independently confirms all three compiler exits. Empty compiler output alone was not treated as a pass.

Initial process inspection found only an unrelated customer-overview fixture Node server, not an earlier compiler/test worker. A later successful process inspection likewise showed only that fixture server before validation. Some subsequent process inspections failed to load CimCmdlets; those are not evidence of process absence.

No deployment/Python/paused Feature2 changes, production writes, cloud builds, dependency installation, or policy modifications were performed. Existing unrelated workspace changes were not reverted.

## Outstanding acceptance work

Run the eight-file focused suite, full UI suite, both Vite production builds, and fixture-only browser checks in an explicitly authorized environment where normal esbuild execution is permitted. Confirm mounted draft identity, pending-save ownership, CAS conflict preservation, scope/race behavior, responsive catalog layout, and customer artwork/copy regression. Do not treat this report or the new regression tests as proof that those runtime checks passed.