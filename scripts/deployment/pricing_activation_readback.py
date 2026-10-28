"""Read-only pricing activation evidence; no restart, settings or secret writes."""
import json
from datetime import UTC, datetime
from urllib.error import HTTPError

from scripts.deployment import pricing_runtime_release as pricing
from scripts.deployment import runtime_rollout as rt


def main():
    import os
    os.environ.update(REQUESTS_CA_BUNDLE=rt.CA, SSL_CERT_FILE=rt.CA)
    review = json.loads((pricing.HOME / "review.json").read_text())
    rt.require((pricing.HOME / "applied.json").exists(), "applied_marker_required")
    result = {"at": datetime.now(UTC).isoformat(), "sites": {}}
    for kind in pricing.KINDS:
        print(json.dumps({"reading": kind, "operation": "site"}), flush=True)
        rid = rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + kind
        properties = rt.arm(rid)["properties"]
        config = rt.arm(rid + "/config/web")["properties"]
        record = {"state": properties.get("state"),
                  "lastModifiedTimeUtc": properties.get("lastModifiedTimeUtc"),
                  "configured_image_matches": config.get("linuxFxVersion") == "DOCKER|" + review["images"][kind]}
        print(json.dumps({"reading": kind, "operation": "instances"}), flush=True)
        record["instances"] = [{"state": x.get("properties", {}).get("state"),
                                "containers": len(x.get("properties", {}).get("containers") or {})}
                               for x in rt.arm(rid + "/instances").get("value", [])]
        try:
            record["sitecontainers"] = [{k: x.get("properties", {}).get(k)
                                         for k in ("image", "isMain", "targetPort")}
                                        for x in rt.arm(rid + "/sitecontainers").get("value", [])]
        except HTTPError as error:
            record["sitecontainers_status"] = error.code
        except ValueError:
            record["sitecontainers_status"] = "non_json_response"
        if kind in ("api", "customer"):
            try:
                raw = rt.arm(rid + "/containerlogs", "POST", raw=True)
                record["logs"] = rt.log_summary(raw)
                record["current_digest_in_logs"] = review["images"][kind].split("@", 1)[1].encode() in raw
            except HTTPError as error:
                record["logs_status"] = error.code
        result["sites"][kind] = record
        rt.save(rt.ROOT / "gateway/validation/pricing-activation-readback-20261027.json", result)
        print(json.dumps({"site": kind, "evidence": record}), flush=True)
    rt.save(rt.ROOT / "gateway/validation/pricing-activation-readback-20261027.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"errorType": type(error).__name__, "detail": "suppressed"}), flush=True)
        raise SystemExit(1)