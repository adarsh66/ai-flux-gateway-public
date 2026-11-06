"""Read nonsecret identity/lifetime for the stopped zero-inference controller.

No inference, no refresh/login, no credential output, no consumed-source edits.
"""
import base64
from datetime import UTC, datetime
import json

from scripts.deployment import foundry_eight_acceptance as a


def main():
    failure = a.load(a.HOME / "failure.json")
    a.require(failure["consumed_alias_count"] == 0 and not (a.HOME / "probes").exists(), "zero_inference_required")
    a.write(a.HOME / "auth-audit-intent.json", {"at": a.now(), "inference": 0, "operation": "existing_cli_token_metadata_only"})
    token = a.cli(["account", "get-access-token", "--subscription", a.rt.SUB,
                   "--resource", "https://management.azure.com/"])["accessToken"]
    part = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    result = {"at": a.now(), "tenant_matches": claims.get("tid") == a.rt.TENANT,
        "operator_matches": claims.get("oid") == a.rt.OPERATOR, "audience": claims.get("aud"),
        "remaining_seconds": int(claims["exp"] - datetime.now(UTC).timestamp()),
        "expected_preflight_minimum_seconds": 900, "inference": 0, "token_not_retained": True}
    token = None
    a.write(a.HOME / "auth-audit-result.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()