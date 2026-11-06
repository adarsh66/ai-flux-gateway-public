"""Explicit Oct30 parent entrypoint. Import/localcheck never activate anything.

Run the reviewed window in a separate live process while the browser-capable
parent watches parent-browser-request.json. Silence means reconcile, not rerun.
Only the callback is time-bounded; killing this process cannot guarantee finally.
"""
import argparse
from pathlib import Path
import ssl

from scripts.deployment import auto_path_diagnostic_oct30 as s

d = s.d
TRUSTED_CA = Path("C:/Users/p4032099/.azure/ca-bundle-zscaler.pem")
TRUSTED_CA_SHA256 = "e747e9880a4e63c73f55af589941139d0a4f90ceec5df745cfd6fee5bbe257dc"


def configure_trusted_transport():
    """Use the existing pinned corporate bundle, never unverified TLS/fallback.

    The historical temporary CA path no longer exists. Change only this
    process's transport configuration, not any consumed source or environment.
    All existing strict openers, hostname checks and no-redirect guards remain.
    """
    d.require(TRUSTED_CA.is_file() and not TRUSTED_CA.is_symlink()
              and d.sha(TRUSTED_CA.read_bytes()) == TRUSTED_CA_SHA256,
              "oct30_exact_existing_trusted_CA")
    context = ssl.create_default_context(cafile=str(TRUSTED_CA))
    d.require(context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED,
              "oct30_verified_TLS_required")
    d.r.rt.CA = str(TRUSTED_CA)
    d.r.rt.ENV = {**d.r.rt.ENV, "REQUESTS_CA_BUNDLE": str(TRUSTED_CA),
                  "SSL_CERT_FILE": str(TRUSTED_CA)}


def checked_package(folder, manifest_sha256):
    d.require(folder.parent == d.r.rt.HOME.resolve()
              and folder.name.startswith("auto-path-oct30-")
              and not folder.is_symlink(), "oct30_exact_package_scope")
    d.require(d.sha((folder / "manifest.json").read_bytes()) == manifest_sha256,
              "oct30_exact_manifest_required")
    return s.localcheck(folder)


def run_parent(folder, manifest_sha256, page_id):
    """Later explicit parent authorization only; never called by preparation."""
    checked_package(folder, manifest_sha256)
    s.controller.review(folder, "install-global")
    s.controller.browser_preflight(folder)
    preflight = d.load(folder / "browser-preflight.json")
    d.require(preflight["page_id"] == page_id, "oct30_actual_parent_page_binding")
    d.require(not any((folder / name).exists() for name in (
        "parent-window-intent.json", "activation-intent.json",
        "browser-send-intent.json", "browser-claim-intent.json",
        "parent-browser-request.json", "parent-browser-response.json",
        *(stage + "-intent.json" for stage in d.STAGES))),
        "oct30_existing_intent_RECONCILE_NEVER_REPLAY")
    d.require(not (folder.parent / "auto-path-diagnostic-attempt-owner.json").exists(),
              "oct30_attempt_already_consumed")
    configure_trusted_transport()
    # run_reviewed_window durably arms its finally before activation. Do not
    # introduce a second cleanup/retry path around it.
    return s.run_reviewed_window(folder, s.ProductionAdapter(folder),
        lambda binding: s.file_browser_handoff(folder, binding))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "localcheck", "run-reviewed-window"))
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--page-id")
    parser.add_argument("--tests", type=Path)
    parser.add_argument("--browser-tests", type=Path)
    parser.add_argument("--proposal-tests", type=Path)
    args = parser.parse_args(argv)
    folder = args.package.resolve()
    d.require(folder.parent == d.r.rt.HOME.resolve()
              and folder.name.startswith("auto-path-oct30-"), "oct30_exact_package_scope")
    if args.stage == "prepare":
        d.require(all(path is not None for path in
            (args.tests, args.browser_tests, args.proposal_tests)), "actual_test_receipts_required")
        d.require(not folder.exists(), "existing_package_never_refresh")
        configure_trusted_transport()
        s.prepare(folder, args.tests, node_receipts=(args.browser_tests, args.proposal_tests))
    else:
        d.require(args.manifest_sha256 is not None, "explicit_manifest_hash_required")
        checked_package(folder, args.manifest_sha256)
        if args.stage == "run-reviewed-window":
            d.require(isinstance(args.page_id, str) and len(args.page_id) == 36,
                      "actual_parent_page_required")
            run_parent(folder, args.manifest_sha256, args.page_id)
    print(d.json.dumps({"status": "COMPLETED_" + args.stage.upper(),
        "manifest_sha256": d.sha((folder / "manifest.json").read_bytes())}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print('{"status":"STOP_RECONCILE_DURABLE_EVIDENCE_NO_RETRY"}', flush=True)
        raise SystemExit(2)