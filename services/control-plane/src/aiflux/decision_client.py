"""Bounded Microsoft Decision-1 System One adapter, never a chat generator.

Request reference: https://learn.microsoft.com/azure/foundry/foundry-models/how-to/use-foundry-models-microsoft-decision
Probability mapping reference: https://learn.microsoft.com/azure/databricks/machine-learning/model-serving/query-systemone-models
The mapping remains a fixture contract until the existing Foundry MI path is proven.
"""
from dataclasses import dataclass
import json
import math
from time import perf_counter
from typing import Any

from azure.core.credentials import TokenCredential
from azure.identity import ManagedIdentityCredential
import httpx

ENDPOINT = "https://poc-ids-token-ex-foundry.services.ai.azure.com/providers/microsoft/v1/systemone"
DEPLOYMENT = "Decision-1"  # Fresh ARM read: Microsoft-Decision-1 v1, DataZoneStandard.
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


class DecisionUnavailable(Exception):
    """Only a timeout, transport failure, or invalid scoring response may degrade."""


class DecisionAccessError(Exception):
    """Authentication, quota, or configuration failure: never silently fall back."""


@dataclass(frozen=True)
class DecisionScores:
    selected_model: str
    probabilities: dict[str, float]
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None


def parse_scores(payload: Any, options: set[str], latency_ms: float) -> DecisionScores:
    try:
        answer = payload["answers"]["route"]
        scores = answer["probabilities"]
        if (answer["type"] != "choice" or answer["choice"] not in options
                or not isinstance(scores, dict) or set(scores) != options):
            raise ValueError("closed_options")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               or not 0 <= v <= 1 for v in scores.values()):
            raise ValueError("probability")
        if not math.isclose(sum(scores.values()), 1, abs_tol=0.02):
            raise ValueError("probability_sum")
        # Stable alias tie-break, not response order or a made-up quality ranking.
        selected = min(options, key=lambda alias: (-scores[alias], alias))
        if scores[answer["choice"]] != scores[selected]:
            raise ValueError("inconsistent_choice")
        usage = payload.get("usage") or {}
        def count(name: str) -> int | None:
            value = usage.get(name)
            return value if type(value) is int and value >= 0 else None
        return DecisionScores(selected, {k: float(v) for k, v in scores.items()}, latency_ms,
                              count("input_tokens"), count("output_tokens"))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise DecisionUnavailable("invalid_scores") from exc


class DecisionClient:
    def __init__(self, *, client_id: str | None = None, timeout: float = 5,
                 credential: TokenCredential | None = None, transport: httpx.BaseTransport | None = None):
        self.credential = credential or ManagedIdentityCredential(client_id=client_id)
        self.timeout, self.transport = timeout, transport

    def score(self, state: dict, instructions: str, criteria: dict[str, str]) -> DecisionScores:
        if not 2 <= len(criteria) <= 10 or len(json.dumps(state).encode()) > 32768:
            raise DecisionAccessError("invalid_decision_configuration")
        started = perf_counter()
        try:
            token = self.credential.get_token(TOKEN_SCOPE).token
        except Exception as exc:
            raise DecisionAccessError("managed_identity_unavailable") from exc
        # No retries, redirects, arbitrary endpoints, shared keys, or insecure TLS.
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout), follow_redirects=False,
                              transport=self.transport) as client:
                with client.stream("POST", ENDPOINT, headers={"Authorization": "Bearer " + token},
                        json={"model": DEPLOYMENT, "state": state, "questions": {"route": {
                            "type": "choice", "instructions": instructions, "criteria": criteria}}}) as response:
                    if 300 <= response.status_code < 500:
                        raise DecisionAccessError("decision_access_or_configuration")
                    if response.status_code != 200:
                        raise DecisionUnavailable("decision_service_unavailable")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 65536:
                            raise DecisionUnavailable("decision_response_too_large")
                    payload = json.loads(raw)
        except (httpx.HTTPError, ValueError) as exc:
            raise DecisionUnavailable("decision_transport_or_json") from exc
        return parse_scores(payload, set(criteria), round((perf_counter() - started) * 1000, 3))