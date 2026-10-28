"""Fresh ACR publication only (all components or ingestion alone).

Exactly one submission per component; failures require explicit reconciliation.
Shared source is bound independently for API, ingester and both portals.
No app, settings, DB or TF writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from datetime import UTC, datetime

from scripts.deployment import finops_release as release
from scripts.deployment import runtime_rollout as rt


def now():
    return datetime.now(UTC).isoformat()


def check_current(manifest):
    rt.require(release.source_manifest() == manifest, "live_build_source_changed")


def build(components=release.COMPONENTS):
    rt.require(components in (release.COMPONENTS, ('ingestion',)), 'unsupported_build_scope')
    account = rt.cli(["account", "show"])
    rt.require(account["id"] == rt.SUB and account["tenantId"] == rt.TENANT, "account_scope")
    manifest = release.source_manifest()
    tag = "finops-" + datetime.now(UTC).strftime("%Y%m%dt%H%M%Sz")
    folder = rt.HOME / "finops" / tag
    rt.require(not folder.exists(), "build_evidence_collision")
    context = folder / "context"
    inventory = {entry["path"]: entry["sha256"] for kind in components
                 for entry in manifest["components"][kind]["entries"]}
    for name, expected in inventory.items():
        path = rt.ROOT / name
        rt.require(release.digest(path.read_bytes()) == expected, "source_changed_while_copying")
        target = context / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    rt.save(folder / "source-manifest.json", manifest)
    result = {"tag": tag, "started_at_utc": now(), "source_manifest_sha256":
              release.digest((folder / "source-manifest.json").read_bytes()), "components": {},
              "requested_components": list(components),
              "application_deployment": False, "settings_writes": 0, "database_writes": 0}
    rt.save(folder / "results.json", result)
    print(json.dumps({"build_folder": folder.relative_to(rt.ROOT).as_posix(),
                      "requested_components": list(components)}), flush=True)
    for kind in components:
        check_current(manifest)
        dockerfile = "services/control-plane/Dockerfile" if kind == "api" else (
            "services/usage-ingestion/Dockerfile" if kind == "ingestion" else f"apps/{kind}-portal/Dockerfile")
        args = rt.CLI + ["acr", "build", "--registry", "pocidstokenexacr", "--subscription", rt.SUB,
            "--platform", "linux/amd64", "--timeout", "1800", "--file", str(context / dockerfile),
            "--image", f"aiflux-{kind}:{tag}"]
        if kind in {"admin", "customer"}:
            for name, value in {"VITE_AUTH_MODE": "local", "VITE_CONTROL_API_URL": "/api",
                "VITE_GATEWAY_URL": "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1"}.items():
                args.extend(["--build-arg", name + "=" + value])
        args.append(str(context))
        item = {"submission_intent_at_utc": now(), "submissions": 1,
                "source_sha256": manifest["components"][kind]["source_sha256"]}
        result["components"][kind] = item
        rt.save(folder / "results.json", result)
        child = subprocess.run(args, cwd=rt.ROOT, env=rt.ENV, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=2100)
        text = re.sub(r'https://[^\s"<>]*\?[^\s"<>]*', '[signed-url-redacted]', child.stdout + child.stderr)
        (folder / (kind + "-build.log")).write_text(text, encoding="utf-8")
        runs = re.findall(r'(?:Run ID:|run ID:|Queued a build with ID:)\s*([a-z0-9]+)', text)
        item.update(cli_exit_code=child.returncode, run_id=runs[-1] if runs else None)
        rt.save(folder / "results.json", result)
        rt.require(child.returncode == 0 and item["run_id"], "build_failed_or_ambiguous_no_resubmit")
        run = rt.cli(["acr", "task", "show-run", "--registry", "pocidstokenexacr", "--run-id", item["run_id"],
                      "--subscription", rt.SUB])
        rt.require(run["status"] == "Succeeded" and run["platform"]["os"].lower() == "linux", "native_build_not_verified")
        image = rt.cli(["acr", "manifest", "show-metadata", "--registry", "pocidstokenexacr",
                        "--name", f"aiflux-{kind}:{tag}", "--subscription", rt.SUB])
        pin = image.get("digest", "")
        rt.require(re.fullmatch(r"sha256:[0-9a-f]{64}", pin), "immutable_pin_required")
        rt.require(run.get("outputImages") == [{"digest": pin, "registry": release.REGISTRY,
            "repository": "aiflux-" + kind, "tag": tag}], "build_output_binding_mismatch")
        item.update(status=run["status"], image=release.REGISTRY + "/aiflux-" + kind + "@" + pin,
                    started_at_utc=run["startTime"], finished_at_utc=run["finishTime"])
        rt.save(folder / "results.json", result)
        print(json.dumps({"component": kind, **item}), flush=True)
    check_current(manifest)
    result.update(exit_code=0, finished_at_utc=now())
    rt.save(folder / "results.json", result)
    print(json.dumps({"build_folder": folder.relative_to(rt.ROOT).as_posix(), "exit_code": 0,
                      "images": {k: v["image"] for k, v in result["components"].items()}}), flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', choices=('all', 'ingestion'), default='all',
                        help='Use ingestion for the bounded catalog-only package repair.')
    args = parser.parse_args()
    try:
        raise SystemExit(build(('ingestion',) if args.component == 'ingestion' else release.COMPONENTS))
    except Exception as exc:
        # Never export CLI response bodies or arbitrary SDK exception strings.
        print(json.dumps({"status": "blocked", "exception_type": type(exc).__name__,
                          "reason": "four_image_build_failed_no_automatic_resubmission"}), flush=True)
        raise SystemExit(2)