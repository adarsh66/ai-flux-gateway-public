# Minimal signed-out login UI validation — 2026-10-28

**Result: deployed and live signed-out browser verified.**

## Live customer-only deployment

- User subsequently authorized deployment to the existing live setup. Production
	customer image build `cm2y` succeeded at 2026-10-28T12:37:30.369806+00:00;
	digest `sha256:a30d513ce0dd7c529491689a49ce311f7794f4785e1dd5c5577ae62da9f1b975`.
- Separate actual validation passed 65 release/portal/compatibility tests and the
	official sequential Azure validation workflow. Preserved target plan SHA256:
	`94e471ad205e2eeea17c27489f350c22d1e3f18c3ab619e966968837c2140f2e`.
	An original full companion read failed; a fresh serial NEVER APPLY companion
	resolved its checks without rebuilding or replanning the customer target.
- Exact saved target applied **once** at 2026-10-28T13:10:52.573981+00:00:
	**0 added, 1 changed, 0 destroyed**. The companion was not applied.
- Independent complete protected readback passed at
	2026-10-28T13:12:47.981427+00:00. All four settings hashes, API/admin/ingestion
	images, current detached fragment, gateway policy/routes/counters and FinOps
	controls remained unchanged. Supplemental RAI policies/bindings, role
	definitions and network hashes matched at 2026-10-28T13:15:33.700849+00:00.
- Live health and customer page returned HTTP200. New customer bundle
	`/assets/index-BH8-pyyw.js` contains sign-in and no removed CTA.
- A separate isolated signed-out browser context loaded the live root HTTP200:
	Sign in, Email and Password visible; both “Create a new OpCo account” and
	“Create account” buttons absent. Shared authenticated tabs were untouched.
	No live credentials submitted, registration request or inference performed.
- Backend registration remains unchanged. Current validated shared UI also
	includes prior Showback/client edits; predecessor delta is explicitly recorded
	in the release scope review rather than asserted to be a CTA-only byte delta.
- Evidence: [.deployment/customer-login-20261028T125500Z/verified.json](../.deployment/customer-login-20261028T125500Z/verified.json),
	[HTTP proof](../.deployment/customer-login-20261028T125500Z/http.json),
	[independent validation](../.deployment/customer-login-20261028T125500Z/validation.json).

The following sections retain the earlier source-only validation history; their
no-deployment statements describe that earlier validation stage only.

## Scope and implementation

- Preserved the parent's minimal change in [auth.tsx](../packages/ui/src/auth.tsx): removed the signed-out registration CTA block and retained the read-only `mode` state. Intentionally unreachable registration branches were not refactored.
- Expanded the existing local-login regression in [token-exchange.test.tsx](../packages/ui/src/token-exchange.test.tsx) to cover both customer and IDS admin portals. Both cases verify absent registration buttons, unchanged default email, zero fetches before submission, exactly one POST to `/api/auth/login` with the expected credentials, and successful authenticated rendering.
- The first-fetch assertion was correct: local signed-out initialization does not call `/auth/me`. The Entra-only membership check is a separate code path.
- No backend, API, Terraform, launcher, dependency, live configuration, or RBAC changes were made by this validation work. Unrelated working-tree edits were left untouched.

## Fresh native Linux validation

Reused the existing explicit `--no-push` source-only launcher [scripts/validate_admin_showback.py](../scripts/validate_admin_showback.py), not any release/native stage or historical intent. It staged a fresh curated context of 74 files and submitted exactly one bounded Linux/amd64 ACR build. The context included both auth source and tests, including current untracked UI sources; backend and Terraform sources were excluded.

| Check | Result |
| --- | --- |
| ACR run | `cm2x` — `Succeeded` |
| Finished (UTC) | 2026-10-28T12:19:29.600474+00:00 |
| Workspace TypeScript checks on Linux | Passed |
| Full UI test suite | **124 passed, 16 test files passed**, zero failures (prior 123 plus the added admin-login case) |
| Customer local-login regression | Passed |
| IDS admin local-login regression | Passed |
| Admin production UI build | Passed, 3.42s |
| Customer production UI build | Passed, 3.41s |
| Separate local TypeScript task | Passed for shared UI and both portals; no local esbuild retry |
| Manifest/source/staged context hashes | All 74 entries independently verified after completion |
| Published images | None; ACR returned `outputImages: [null]` |
| Deployment | None |

Both production builds were ephemeral validation outputs only. Vite reported non-failing large-chunk warnings; no optimization/refactoring was added to this minimal change.

## Completion artifacts

- [Completion report](../.deployment/admin-showback-native-20261028T121721699258Z/completion.json)
- [Original launcher result](../.deployment/admin-showback-native-20261028T121721699258Z/result.json)
- [Source hash manifest](../.deployment/admin-showback-native-20261028T121721699258Z/sources.json)
- [Explicit no-push intent](../.deployment/admin-showback-native-20261028T121721699258Z/build-intent.json)
- [Native validation log](../.deployment/admin-showback-native-20261028T121721699258Z/validation.log)

Source manifest SHA-256: `91443fba5fe909624fde27f1b0e6a54783fe74a8536acf0698c02231604921c4`.

Auth source SHA-256: `cf5682479e269f60b9616cb64dac22e0f825367d4c387b3c7fcf5ee11c1a834a`.

Auth test SHA-256: `0d13ecbc9e51ff2d0b0e776c32121a97ebbe2ef3f4d9517a4ca0081c8bd09262`.

Validation log SHA-256: `2fb1383ee2d3cb61d1b342300c5258f49e7b3bc94f4321fd069600547ca50f67`.

Original result SHA-256: `8466274f6252c9f105d734e2a3c19758c4277828068e6c2a0788904cc2e07275`.

Only bounded ACR validation compute/source upload and account/registry/run metadata reads were used. No image tag/push, deployment plan/apply, live configuration change, RBAC grant, or historical workflow replay occurred.