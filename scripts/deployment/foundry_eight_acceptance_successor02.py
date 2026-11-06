"""Zero-send, content-negotiation successor; no inference retries.

requests' default Accept:*/* made ARM return policy XML instead of its JSON
envelope. Explicit application/json restores the existing reader contract;
no alternate endpoint, relaxed policy hash or XML reinterpretation is allowed.
"""
from pathlib import Path
from types import FunctionType

from scripts.deployment import foundry_eight_acceptance_successor as prior

a = prior.original
HOME = a.rt.HOME / "foundry-eight-acceptance-20261031-successor02"
AUDIT = a.rt.HOME / "foundry-eight-acceptance-read-audit01"


class JSONClient(prior.FreshClient):
    def __init__(self):
        super().__init__()
        self.session.headers["Accept"] = "application/json"


def predecessor():
    result = prior.predecessor()
    failure = a.load(prior.HOME / "failure.json")
    a.require(failure["consumed_alias_count"] == 0 and failure["error_type"] == "JSONDecodeError"
        and not (prior.HOME / "probes").exists(), "second_predecessor_zero_sends_required")
    previous = a.load(prior.HOME / "source-binding.json")
    a.require(all(a.sha((a.ROOT / path).read_bytes()) == digest for path, digest in previous.items()),
              "second_predecessor_all_bound_bytes_exact")
    shape = a.load(AUDIT / "policy-wire-shape.json")
    parsed = a.load(AUDIT / "failure.json")
    a.require(shape["status"] == 200 and shape["content_type"].startswith("application/vnd.ms-azure-apim.policy+xml")
        and parsed["document_starts_xml"] and parsed["inference"] == 0, "actual_xml_content_negotiation_diagnosis")
    for folder in (prior.HOME, AUDIT):
        result.update({p.relative_to(a.ROOT).as_posix(): a.sha(p.read_bytes()) for p in folder.rglob("*") if p.is_file()})
    return result


def inputs():
    return {**prior.inputs(), **predecessor(),
        Path(__file__).relative_to(a.ROOT).as_posix(): a.sha(Path(__file__).read_bytes()),
        "tests/unit/test_foundry_eight_acceptance_successor02.py": a.sha(
            (a.ROOT / "tests/unit/test_foundry_eight_acceptance_successor02.py").read_bytes())}


def main():
    predecessor()
    scope = {**a.run.__globals__, "HOME": HOME, "Client": JSONClient, "inputs": inputs, "__file__": __file__}
    return FunctionType(a.run.__code__, scope, "successor02_run")()


if __name__ == "__main__":
    raise SystemExit(main())