"""Zero-send predecessor successor: acquire valid ARM auth per metadata read.

No inference retry. Original failure/zero probe directory/source bindings must
remain exact. The inference implementation and its eight-request budget are
unchanged. A 900-second lease for an entire inference run was unnecessary: ARM
auth is never used for inference, only for individual <=90-second metadata reads.
"""
import base64
from datetime import UTC, datetime
import json
from pathlib import Path
from types import FunctionType

import requests
from requests.adapters import HTTPAdapter

from scripts.deployment import foundry_eight_acceptance as original

HOME = original.rt.HOME / "foundry-eight-acceptance-20261031-successor01"
PREVIOUS = original.HOME


def predecessor():
    failure = original.load(PREVIOUS / "failure.json")
    original.require(failure["consumed_alias_count"] == 0 and failure["successful_aliases"] == []
        and failure["reason"] == "current_arm_identity_expiry" and not (PREVIOUS / "probes").exists(),
        "predecessor_must_prove_zero_inference")
    bindings = original.load(PREVIOUS / "source-binding.json")
    original.require(all(original.sha((original.ROOT / p).read_bytes()) == h for p, h in bindings.items()),
                     "consumed_predecessor_sources_must_remain_exact")
    audit = original.load(PREVIOUS / "auth-audit-result.json")
    original.require(audit["tenant_matches"] and audit["operator_matches"] and audit["inference"] == 0
        and audit["audience"] == "https://management.azure.com/" and 0 < audit["remaining_seconds"] < 900,
        "exact_auth_lease_diagnosis")
    return {p.relative_to(original.ROOT).as_posix(): original.sha(p.read_bytes())
            for p in PREVIOUS.rglob("*") if p.is_file()}


class FreshClient(original.Client):
    def __init__(self):
        original.require(Path(original.rt.CA).is_file(), "existing_trusted_ca_required")
        account = original.cli(["account", "show"])
        original.require(account["id"] == original.rt.SUB and account["tenantId"] == original.rt.TENANT
            and account["state"] == "Enabled", "current_account_scope")
        self.token = None
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=0))
        self.session.verify = original.rt.CA

    def arm(self, path, *, secret=False):
        token = original.cli(["account", "get-access-token", "--subscription", original.rt.SUB,
                              "--resource", "https://management.azure.com/"])["accessToken"]
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        original.require(claims["tid"] == original.rt.TENANT and claims["oid"] == original.rt.OPERATOR
            and claims["aud"] == "https://management.azure.com/"
            and claims["exp"] > datetime.now(UTC).timestamp() + 100, "current_per_read_arm_identity_expiry")
        self.token = token
        try:
            return super().arm(path, secret=secret)
        finally:
            self.token = None
            token = None


def inputs():
    return {**original.inputs(), **predecessor(),
        Path(__file__).relative_to(original.ROOT).as_posix(): original.sha(Path(__file__).read_bytes()),
        "tests/unit/test_foundry_eight_acceptance_successor.py": original.sha(
            (original.ROOT / "tests/unit/test_foundry_eight_acceptance_successor.py").read_bytes())}


def main():
    predecessor()
    # Private globals, not a module-global monkeypatch: original source/receipts
    # and direct invocation still permanently point to the consumed predecessor.
    scope = {**original.run.__globals__, "HOME": HOME, "Client": FreshClient,
             "inputs": inputs, "__file__": __file__}
    run = FunctionType(original.run.__code__, scope, "successor_run")
    return run()


if __name__ == "__main__":
    raise SystemExit(main())