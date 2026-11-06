"""Release-owned output limits, separate from historical gateway smoke evidence.

The same JSON bytes are supplied to project-route and the API image. Loading a
contract validates configuration, NOT provider compatibility or live acceptance.
No contract means the existing inventory/catalog ceilings remain authoritative.
"""
import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from aiflux.default_limits import COMPLETION_ALLOWANCE

TokenLimit = Annotated[int, Field(strict=True, ge=1, le=COMPLETION_ALLOWANCE)]


class CompletionLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Annotated[Literal[1], Field(alias="schema")]
    allowance: TokenLimit
    provider_limits: dict[str, Annotated[int, Field(strict=True, ge=1, le=1000000)]]


def load(settings, aliases: set[str]) -> tuple[CompletionLimits, str] | None:
    path = settings.gateway_completion_limits_path
    if path is None:
        return None
    with path.open("rb") as stream:
        raw = stream.read(16384)
    if len(raw) > 16383:
        raise ValueError("Completion limit contract exceeds supported capacity")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate completion limit key")
            result[key] = value
        return result

    decoded = json.loads(raw, object_pairs_hook=unique)
    if (type(decoded) is not dict or type(decoded.get("schema")) is not int
            or raw != json.dumps(decoded, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False).encode("utf-8")):
        raise ValueError("Completion limits require canonical UTF-8 JSON with integer schema")
    value = CompletionLimits.model_validate(decoded)
    if type(value.schema_version) is not int or set(value.provider_limits) != aliases:
        raise ValueError("Completion limits must bind the exact accepted chat aliases")
    if (type(settings.gateway_max_completion_tokens) is not int
            or settings.gateway_max_completion_tokens != value.allowance):
        raise ValueError("Gateway setting and completion allowance disagree")
    return value, hashlib.sha256(raw).hexdigest()


def effective(settings, alias: str, historical: int, contract=None) -> int:
    """One ceiling for catalog, Auto descriptors and subsequent price publication."""
    if contract is not None:
        value, _ = contract
        return min(value.allowance, value.provider_limits[alias])
    return min(COMPLETION_ALLOWANCE, historical,
               settings.gateway_max_completion_tokens or historical)


def snapshot_version(original: str, contract) -> str:
    # Keep historical receipts valid without opt-in; a successor cannot reuse
    # a 1024 receipt or stale price pool binding after changing output limits.
    return original if contract is None else hashlib.sha256(
        f"{original}:{contract[1]}".encode("ascii")).hexdigest()