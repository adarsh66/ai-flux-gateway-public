# Admin-only defaults rollout — verified

The already-built Admin cm5a image was deployed with the exact saved Admin31 plan **once**, native exit 0. Plan SHA-256: 70b548f5e5ca58b73efff7335b41f7a6c8c1b7092e3e972f4bcecaa1549f84d9. Image digest: f55d486010f1d32dbce2b092c6aaacce732794623c0ca8963870134525fc6f4c.

## Diagnosis and preservation

- Original preapply failure was not a generic permission blocker: ARM token remaining lifetime fell from 609.52 to 599.90 seconds after six successful reads. The next request was rejected by TTL600 before either apply intent existed.
- New exclusive continuation used the installed CLI Profile acquisition, exact ARM/Storage audience scopes, verified tenant/operator and unchanged per-request TTL600. Supported silent renewal was available and tested; the actual fresh ARM token was already healthy (4881.59 seconds), so no force refresh or login was needed.
- Fresh full preguards passed. The sole admin apply completed at recorded host UTC 2026-11-01T16:57:25Z (session label Nov 02).
- Original postguard reporting failure is preserved. Independent retained-only reconciliation proved two additional provider-owned image mirrors in Admin site detail: siteConfig.linuxFxVersion and siteProperties.LinuxFxVersion. All other recursive fields remain exact; no broad waiver or read/apply replay.
- Root state 141→142 changes only the admin image and computed mirrors, serial, and the exact complete saved-plan check projection. Child state remains 201.
- Complete settings for all four runtimes, all 22 models, all policy formats, backends, revisions, identity, roles, network and security remain exact. API, customer and ingestion pins are unchanged.
- Prior CAS 12→13 changed only inherited default literals and one default call-cap literal. Typed pricing projection, explicit overrides, safety, ownership, counter keys and reset semantics remain exact. Unknown stored-envelope preservation is source-bound, not a claimed raw database readback.

## Live acceptance

HTML, JavaScript and CSS were independently read from digest-verified existing cloud-image layers and compared byte-for-byte with live HTTP 200 assets:

| Asset | SHA-256 |
|---|---|
| Admin HTML | 71653a4f62ba42f7d629e9ae6df0a0318124d5dde3611dc15c6254ffeae52b20 |
| index-CgQ6JdP-.js | b55abc5a7d9a8db91456618baceaefb66c29fd8b2762ed9b8bb1f7a95ead7249 |
| index-dHM_aeWN.css | b5bae5afc0405aeb3dfdf45344891ef236b3499c006ae63c885d4a8b1f16f322 |

The existing authenticated browser was reloaded. Admin settings GET returned 200; revision 13 / published 13 and the visible form both show **60 RPM, 300,000 TPM, 20,000,000 daily tokens, 50,000 calls per 86,400 seconds**. No settings save, checkbox approval, login or inference was performed.

The first registry blob read failed because registry Bearer authorization was forwarded to its signed Storage redirect. That failure remains retained; a separately named missing-read continuation reused the successful manifest and validated HTTPS blob redirects while removing cross-host authorization. No image build or manifest replay.

## Budget and remaining scope

One admin saved-plan apply; zero builds, pushes, new ACR runs, official-workflow replays, API/gateway/CAS replays, paid inference or security/network/role changes. Two explicit authenticated readback GETs and one browser reload; automatic page GETs were not separately counted.

Shared pricing remains **PAUSED**: no pricing workflow entrypoints, pool changes or price updates. Output allowance remains **1024**, retries 0. **4096 is not implemented; the broader task is not complete.** Publication/UI readback is verified, not paid traffic acceptance.

Endpoint: https://poc-ids-token-ex-admin.azurewebsites.net/admin/settings

Authoritative retained receipts: [final report](../.deployment/default-limits-runtime-20261102-01/admin31/continuation32/FINAL-REPORT.json), [independent postproof](../.deployment/default-limits-runtime-20261102-01/admin31/continuation32/INDEPENDENT-POSTPROOF.json), [asset proof](../.deployment/default-limits-runtime-20261102-01/admin31/continuation32/assets33/ASSETS-VERIFIED.json), [authenticated browser proof](../.deployment/default-limits-runtime-20261102-01/admin31/continuation32/BROWSER-GET-VERIFIED.json).