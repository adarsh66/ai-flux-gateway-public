# Gateway successor19 — source fixed; deployment blocked

Gateway18's HTTP400 rejected `System.Globalization.NumberStyles`. Its one saved-plan apply is consumed and must never be replayed; the failed Terraform attempt changed child-state metadata, but protected cloud readback remained unchanged.

The canonical gateway source now validates decimal strings using strict ASCII regex and manual bounded decimal accumulation: maximum 100000, at most eight fractional digits, overflow checked before multiplication. Unknown prices remain null; explicit zero and source strings remain unchanged. No new admission gate or weakened pricing checks were introduced.

The whole new pricing expression was audited against the official APIM allowed-types list. Unsupported globalization and Json.NET serializer settings/date/escape enums were removed. Permitted JsonConvert parsing uses a disposable string-value prefix view to preserve date-shaped provenance; permitted StringBuilder serialization preserves canonical sorted ASCII hashing. Encoding and SHA256 calls are permitted.

107 actual corrected-candidate native C# tests passed, including four cultures, boundaries, comma/exponent/negative/huge/Unicode malformed rates, canonical Unicode/reordered/date provenance, unknown/zero semantics, scoring/result metadata, and fresh typed current projection. Exact raw candidate SHA256: `74cd8ccca8c45a63edfa3c8857ba648034fa74a910a0dc3acc6765096b0d849b`. Inverse raw splice and protected outbound/on-error FinOps suffix are byte-exact. This is offline evidence, not APIM acceptance.

Fresh capture stopped at the unchanged >600-second token guard. Identity/audience matched, but remaining ARM lifetime was approximately 416 seconds. Normal SAME installed CLI ARM login process 10660 (parent 24516) remains pending after a finite 120-second wait. No duplicate login, token manipulation, guard waiver, plan, official validation, or apply was performed.

Complete that ORIGINAL sign-in directly in its terminal/browser, then reconcile the process before any successor capture. The partial baseline and original STOP must remain immutable. A separately named fresh capture/composition is required; retained offline outputs are not fresh deployment authority. Then produce a new gateway-only saved plan with exact semantic lineage, run every official validation step, apply that plan once, and verify full protected postguards. Do not run the current opening/compose entrypoints against their occupied output paths without a new labeled continuation.

Explicit parent result: gateway19 NOT LIVE; gateway18 NOT APPLIED; API cm52 prior deployment untouched; admin cm51 built artifact untouched and not deployed in this stage. No API builds/deploys, paid inference, rate-value writes, role/identity/network/DDL/customer/ingestion changes.

Evidence: [successor19 FINAL](../.deployment/auto-shared-ratecard-20261101-01/gateway-admin19/FINAL.json), [native test results](../.deployment/auto-shared-ratecard-20261101-01/gateway-admin19/offline/native-candidate19.xml), [permitted-type audit](../.deployment/auto-shared-ratecard-20261101-01/gateway-admin19/offline/permitted-types.json).