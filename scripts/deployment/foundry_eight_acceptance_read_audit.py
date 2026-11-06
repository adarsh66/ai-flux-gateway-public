"""One read-only policy response-shape diagnosis; never inference or replay."""
import json
from pathlib import Path
import traceback

from scripts.deployment import foundry_eight_acceptance_successor as s

a = s.original
HOME = a.rt.HOME / "foundry-eight-acceptance-read-audit01"


class Audit(s.FreshClient):
    def wire(self, method, url, **kwargs):
        status, headers, raw = super().wire(method, url, **kwargs)
        normalized = {k.lower(): v for k, v in headers.items()}
        a.write(HOME / "policy-wire-shape.json", {"at": a.now(), "status": status, "bytes": len(raw),
            "body_sha256": a.sha(raw), "content_type": normalized.get("content-type"),
            "starts_json": raw.lstrip().startswith(b"{"), "starts_xml": raw.lstrip().startswith(b"<"),
            "inference": 0})
        return status, headers, raw


def main():
    failure = a.load(s.HOME / "failure.json")
    a.require(failure["consumed_alias_count"] == 0 and not (s.HOME / "probes").exists(), "zero_inference_required")
    HOME.mkdir(exist_ok=False)
    a.write(HOME / "intent.json", {"at": a.now(), "policy_get_max": 1, "inference": 0})
    client = None
    try:
        client = Audit()
        value = client.arm(a.APIM + "/apis/aiflux-dev-unified/policies/policy?format=xml")
        a.write(HOME / "result.json", {"at": a.now(), "policy_object_parsed": True,
            "policy_property_found": isinstance(value.get("properties", {}).get("value"), str), "inference": 0})
    except Exception as error:
        result = {"at": a.now(), "error_type": type(error).__name__, "inference": 0,
            "frames": [{"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                       for frame in traceback.extract_tb(error.__traceback__)]}
        if isinstance(error, json.JSONDecodeError):
            result.update(json_error_position=error.pos, document_characters=len(error.doc),
                document_starts_json=error.doc.lstrip().startswith("{"), document_starts_xml=error.doc.lstrip().startswith("<"))
        a.write(HOME / "failure.json", result)
        print(json.dumps(result), flush=True)
        return 2
    finally:
        if client is not None:
            client.close()
    print(json.dumps(a.load(HOME / "result.json")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())