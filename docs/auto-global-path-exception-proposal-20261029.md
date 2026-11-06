# Owned revision2 path intersection — OFFLINE proposal, pending authorization

**PROPOSAL_PENDING_EXPLICIT_NARROW_AUTHORIZATION_NOT_VALIDATED.**
No global-policy exception is authorized by autonomous work, earlier diagnostic
approval, passing fixtures, or this document. The existing global-immutability
requirement remains binding. If it is absolute, the live diagnostic remains
blocked. No fresh window, manifest, owner, saved plan, publication receipt or
mutation executor is created here. No cloud requests, builds, resource writes,
browser actions, credential access, scoring or completions are performed.

This is a separate proposal following the
[incompatible inherited-path finding](auto-live-release-preparation-20261029.md).
That document and every old bound controller, policy template, source, cleanup
artifact and customer cm38 worker file are deliberately left untouched. New
JavaScript lives outside the deployment Python source glob; no historical
controller is imported or invoked. New test receipts are separate root-level
artifacts, not additions inside historical diagnostic folders.

## Retained facts, not fresh observations

The global policy's four literal paths exclude the revision-suffixed diagnostic
path. With the suffix retained, global rejects; with it stripped, diagnostic06
rejects. The offline tests reproduce this empty intersection using actual retained
policy strings, including diagnostic06's integer UTC ticks. No live rejection or
APIM interpretation is inferred from this model.

The pure [renderer](../scripts/proposals/auto_global_path_exception.mjs) accepts
only these exact predecessor **UTF-8 policy-value bytes**:

| Input | SHA256 |
| --- | --- |
| Global XML-export string from retained diagnostic01 capture | 936a862488c18ea2f11d27bfbe99f653b26edead85546eda171cdb7229600d31 |
| Frozen diagnostic06 policy document | 1897a95092b04282ae75b30194a5c7f0915230235d35114fa03dd3c1464df930 |

The global hash also matches the export hash reported by the later release
preparation research. It is **not** a rawxml/wire-body/envelope hash. Existing
source-template hash, rawxml representation and XML-export hash must never be
substituted for each other. The renderer does not recapture or bless current
state, accept arbitrary predecessor hashes, normalize XML, or serialize an
entire policy tree. The one observed extra global XML-export entity layer is
handled explicitly; diagnostic XML has its ordinary single XML layer.

## Exact finite proposal scope

Let `N` denote the original global normal-path admission expression, unchanged.
Let `E` denote the conjunction below. Proposed global rejection is
`(!N) && (!E)` instead of `!N`. Proposed diagnostic scope rejection is `!E`.
The normal-path expression itself is retained, not replaced with `true` or a
broader route match. No global branch is added before the denial choose.

`E` requires **every** item:

1. `context.Api != null`; exact `context.Api.Id` in the finite set
   `aiflux-dev-unified`, `aiflux-dev-unified;rev=2`; and exact string
   `context.Api.Revision == "2"`. These are two identifier representations of
   the **same owned logical API**, not permission for another API or revision.
   No full ARM-ID acceptance, prefix, case folding, validation API or legacy API.
   The offline model covers both; actual global-scope runtime values have not
   been observed here. Any other representation must fail closed, not be added
   ad hoc. Revision1 with either allowed ID is rejected by `E`.
2. `context.Subscription != null`, `context.Product != null`, exact subscription
   `e9f2abb0-930b-598a-b210-0ab0b279127f`, exact product `aiflux`.
3. Exact `context.Request.Method == "POST"` and platform-observed
   `context.Request.IpAddress == "167.103.66.248"`. No subnet, forwarded-header,
   mapped-IPv6, tenant or permanent-IP allowance. A browser egress observation
   at another destination is not proof APIM sees that address.
4. Exact `context.Request.OriginalUrl.Path` in the finite set
   `/dev/llm/v1;rev=2/chat/completions`, `/dev/llm/v1/chat/completions`.
   The latter supports revision-suffix stripping **only together with the trusted
   API revision2/identity checks**. It does not activate normal current revision1
   Auto. No suffix/prefix match, decode, path normalization, effective-URL rewrite,
   alternate revision, models path, trailing slash or arbitrary operation.
5. One shared UTC start-inclusive/end-exclusive interval, maximum 30 minutes.
   Both predicates derive **identical** start/end integer .NET ticks from the
   same two canonical UTC inputs. No request-derived time, rolling duration,
   independent cleanup deadline, environment override or default current clock.

At global policy scope, APIM's trusted `Subscription` and `Product` context
properties may be referenced. A null value closes this exception; subscription
keys/headers are not parsed or copied to synthesize those properties. Product
context for an all-APIs/API-scoped subscription can be null and is deliberately
not accommodated. Policy expressions do not expose a subscription `State` check;
existing preflight must still verify the exact active product subscription,
product/API association, required subscription flag, owned revision description,
revision2 noncurrent and original current1. Passing a mock context is not
subscription authentication or an active-subscription proof.

### Only two allowed policy spans, no security bypass

| Artifact | Complete permitted delta |
| --- | --- |
| Global policy value | One inbound denial `<when>` condition attribute only: additive exception above |
| Owned diagnostic revision2 value | Its one `diagnostic_scope_closed` `<when>` condition attribute only: matching shared scope |

Every byte outside these attributes is unchanged, including whitespace, newline
style, XML escaping, all bodies and global on-error responses. Reverse-splicing
the two spans reconstructs the original buffers exactly. `assertExactProposal()`
rejects **any** other byte difference, including formatting-only changes.

Normal path requests retain their original admission decisions; all nonexception
requests receive exactly the original global behavior. Normal-path original
response/header/on-error bytes are untouched. A wrong-scope canonical path may
still be admitted by `N`, as before; it is not newly admitted by `E`, and the
diagnostic rejects it. This proposal is not a new general deny policy.

CORS then `<base>` then diagnostic guard ordering stays intact. Product/API
authentication, original quotas, PII handling, both input safety scans, fixed
benign input, exact gateway managed identity/scorer, terminal response and
no-completion behavior all remain byte-identical. No additional forward/retry,
operation, API, subscription, product, role, network, tenant setting, named value,
feature flag, portal image or database change is allowed. Existing terminal
diagnostic budget remains scoring1/completion0/retry0 with its original quota;
the proposal does **not** replenish a consumed attempt or authorize another one.

The test interval is the **expired historical fixture**
2026-10-29T10:16:50Z through 10:46:50Z. It is not a fresh window reservation.
Rendered buffers exist only in test memory. Frozen06 remains consumed, offline
and noncurrent according to its retained evidence; no live claim is made here.
An operational successor would require its own explicit single-attempt approval
and independently reviewed new source/package bindings. Do not execute the
fixture buffers or silently change their nonce/quota/date to reuse old executors.

## Cleanup contract to review BEFORE any future approval/write

`assessGlobalCleanup()` is a pure mocked precondition check, not an ARM request
builder/executor and not authorization. Its tests require the known original
export hash, exact expected candidate bytes, valid opaque post-install ETag and
matching fresh observed ETag. Wildcard, missing/unquoted/header-injected ETags,
candidate drift, predecessor replacement and ETag races stop the assessment.
It returns the exact original export bytes/hash and required conditional
`If-Match`, with retry0 and no time-based obstacle to cleanup.

Any separately authorized operational design MUST additionally:

1. Capture exact original **rawxml bytes/hash AND exported value bytes/hash**
   and opaque ETags for global and owned revision policy before mutation;
   bind them to one immutable manifest, the approved two-span delta, single
   start/end, full13/supplemental baseline and state-owner identity. No stale
   historical ETag or hash-only substitution. These fresh artifacts are **not
   available or claimed here**, so this is not a deploy-ready rollback package.
2. Review one exact global policy target (not a broad Terraform plan), candidate
   hash and fresh predecessor ETag. A later authorized install must use exact
   conditional `If-Match`, no wildcard, redirect, retry, drift adoption or
   unconditional overwrite. Persist intent before wire effects; unknown consumes
   the step and requires reconciliation, never reapplication.
3. Never expose the exception while an unreviewed/general completion policy is
   online. Keep revision2 offline until its terminal fixed-budget diagnostic
   and global scope have actual readbacks and independent approval. No current1
   or protected API substitution. A partial failure closes/stays offline.
4. Close/take owned revision2 offline on success, failure, cancellation, timeout
   or unknown outcome. Restore exact original global value/rawxml using the
   freshly verified installed candidate ETag in `If-Match`; never the preinstall
   ETag. HTTP412 or any candidate/ETag drift means **stop and reconcile with the
   owner**, no `*`, blind retry or clobbering another writer. Keep rev2 offline.
   Restore the owned policy to its bound pre-successor bytes as separately
   reviewed. A candidate already absent needs read-only reconciliation, not
   automatic reinstallation/restoration.
5. Cleanup is required even after the **same** end instant, without needing a
   new activation approval or successful scorer response. Expiry disables `E`
   but does not restore policy bytes, revoke online state or prove cleanup.
   Independent verification must establish original global hashes in both
   captured representations, owned revision offline/noncurrent, original current1,
   all13/supplemental/state and no unrelated drift. This explicitly approved
   temporary global delta would need its own finite full13 comparison rule;
   do not edit the existing immutable-global guard to make old packages pass.

No executor, schedule, mutation intent, fake approval or `Validated` status is
implemented. These requirements remain blockers, not inferred permissions.

## Offline test evidence and limits

[Tests](../tests/auto_global_path_exception.test.mjs) use built-in Node tests,
crypto and a restricted scalar predicate translation in an isolated JS VM.
No esbuild/Vite/Vitest, C# compilation, subprocess, package install, build or
network is used. The renderer imports crypto only, has no filesystem or HTTP
interface and never reads the current clock.

The [passing receipt](../.deployment/auto-global-path-proposal-offline-tests-ticks-20261029.xml)
records **68 passed, 0 failed, 0 skipped**. Coverage includes actual retained
hashes; original empty intersection; both path forms and both finite API-ID
forms; exact reverse-splice byte preservation; normal-path decision matrix;
null/wrong identities/subscription/product; revisions1/3 and numeric/missing
revision; methods/IP/path variants; header/query spoofing; exact time boundaries;
interval injection/extension; arbitrary scope keys; extra base/safety/quota/MI
changes; and expiry-independent conditional cleanup drift/ETag failures.

The [initial receipt](../.deployment/auto-global-path-proposal-offline-tests-20261029.xml)
is retained honestly: 58 passed, 1 failed because the original predicate used
C# long tick literals unsupported by the first mock translator. The corrected
model uses exact BigInt ticks rather than imprecise JavaScript numbers.

These are source/fixture tests, **not** APIM C# validation, global-scope runtime
context proof, fresh protected-resource verification, IP proof, independent
native review, authorization, a real scoring response or a publication receipt.
Remaining runtime, browser actionability and production acceptance gates in the
release preparation document are unchanged. No task-complete signal is made.

### Additional retained-source audit: disclosed historical mismatch

The subsequent [expanded final receipt](../.deployment/auto-global-path-proposal-offline-tests-final-20261029.xml)
records **68 passed, 1 failed**: the added historical diagnostic06 source audit
finds [packages/ui/src/pages/PlaygroundPage.tsx](../packages/ui/src/pages/PlaygroundPage.tsx)
differs from its old manifest binding. This task did not edit that file; the
workspace already contains a later customer Send successor. The mismatch is
retained as a failure, not waived or repaired to make06 executable. All 68
proposal/negative/cleanup tests still pass. No claim that all historical06
sources currently match may be made. The combined audit stopped before checking
customer inputs, so the separate
[customer binding test](../tests/auto_global_path_customer_bindings.test.mjs)
checks that retained current customer input set independently. Neither audit
invokes or alters any existing worker, controller or manifest.
The separate [customer receipt](../.deployment/auto-global-path-customer-bindings-20261029.xml)
records **1 passed, 0 failed**: the current retained customer input hashes match.