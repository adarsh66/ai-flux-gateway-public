# Customer Send repair — live checkpoint, 2026-10-29

## Deployed, independently verified

Native validation cm37 passed160 UI tests/17files, all3 TypeScript checks and
both portal production builds. Source fixes add a synchronous in-flight gate,
bounded15-second credential retrieval, cancellation during preparation, and
late-result suppression after cancellation/reset/unmount/subscription changes.
No retries or fabricated completion usage were introduced.

The separately reviewed customer-only native build cm38 published immutable
digest `5f55df7d5fbc094f37011906c503e96b8c01e329978d6bca9ac9a7d8318eb589`.
The exact saved plan SHA256
`8422682296929ac7c8d2dfbfe709c2728eb9800c13b01df85cbf48c8fc23f1ba`
was applied once at11:52:12 UTC: exit0,0added/1changed/0destroyed.
The companion plan was never applied.

[Independent verification](../.deployment/customer-send-cm38-independent-complete-20261029T120614657632Z/result.json)
completed12:06:58 UTC: full13 equal except the approved customer-image change;
all4 settings and other3 images equal; global/current1/revision2 policies,
routes, subscribers, roles and networks unchanged. Revision2 offline/noncurrent;
project state185 byte-identical; runtime110→111 changed only serial and the
two expected image representations. Lease unlocked, zero deployment workers.
Customer endpoint GET returned200. This is deployment proof, not successful
live inference or complete browser-functional acceptance.

## Browser automation evidence and limits

Earlier shared-page Send clicks timed out waiting for stability while the
document reported hidden. One empty-message Ctrl+Enter reached validation;
this did not prove later keyboard delivery or a working scoring request.
Diagnostic05b then exposed missing timer globals in the automation sandbox;
diagnostic06 used a timer-free helper and returned keyboard1/observedPOST0,
no HTTP response and no scorer proof. Both are consumed, never replayed.
Actual06 cleanup at10:32:24 proved offline/noncurrent/full13 exact.

After the customer deployment, page reload selected the new asset. At12:08,
an actual-page local fixture attempted to fulfill credential retrieval with a
clearly synthetic key and abort all gateway POSTs: neither route was observed.
No successful fixture-to-POST transition or real scoring request is claimed.
A subsequent empty-input keyboard-delivery probe installed a read-only DOM
keydown observer; it recorded zero events after the automation keyboard call.
The page still reported hidden. Later readback also failed to confirm the
requested empty input. Treat these shared-page interaction results as
unreliable, not proof of an application or APIM failure. Fixture routes were
removed at12:08:58 after verified offline; no keys/headers/storage were read.

A newly opened portal tab required sign-in. Credentials were neither requested
through the model nor extracted from another session. A responsive, visible,
authenticated browser is still needed for trustworthy live acceptance.

## Auto remains disabled; no new authorization inferred

The global ordinary-path gate and diagnostic revision-path gate have an empty
intersection. See [release preparation](auto-live-release-preparation-20261029.md)
and the [offline scoped correction proposal](auto-global-path-exception-proposal-20261029.md).
The proposal passed68 offline tests but is not deployed or Validated.
No global exception, new role, network rule, tenant approval gate or DDL was
introduced. The existing state ACL already admitted167.103.66.248; no ACL write
was needed. Public browser egress to a repository-known IP service matched that
address, but APIM-observed source IP remains unproven.

User was unavailable for the specific global-scope question and requested
autonomous work. This was not recorded as explicit approval of the previously
protected global-policy change. Auto runtime scoring/schema, separate persisted
decision overhead, genuine policy publication receipt, API release and default
customer onboarding acceptance remain incomplete. Do not mark the overall task
complete or replay historical diagnostic/build/plan/apply operations.