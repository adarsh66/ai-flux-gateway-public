"""Schema-3 operator defaults; legacy schema-1/2 contracts remain unchanged."""
from copy import deepcopy

POC_RPM = 60
POC_TPM = 300_000
POC_DAILY_TOKENS = 20_000_000
POC_DAILY_CALLS = 50_000
COMPLETION_ALLOWANCE = 4096
POC_DEFAULT_LIMITS = {
    "rpm": POC_RPM, "tpm": POC_TPM,
    "token_quota": POC_DAILY_TOKENS, "request_quota": POC_DAILY_CALLS,
}


def defaults_only_envelope(stored: dict) -> dict:
    """Copy just global limits, retaining unknown JSON, bindings and pricing.

    This is not a history migration or an implicit read-time change. The caller
    must append an audited revision under CAS and verify its live predecessor.
    """
    result = deepcopy(stored)
    configuration = result.get("configuration")
    if not isinstance(configuration, dict) or type(configuration.get("schema_version")) is not int or configuration["schema_version"] != 3:
        raise ValueError("Default-limit migration requires existing schema 3")
    defaults = configuration.get("defaults")
    if not isinstance(defaults, dict):
        raise ValueError("Existing explicit global limits are required")
    defaults.update(POC_DEFAULT_LIMITS)
    return result


def global_defaults_status(stored: dict | None, version: int, published_version: int | None) -> dict:
    """Report stored strict defaults, never claim detached inline enforcement."""
    configuration = stored.get("configuration") if isinstance(stored, dict) else None
    defaults = configuration.get("defaults") if isinstance(configuration, dict) else None
    valid = (isinstance(configuration, dict)
             and type(configuration.get("schema_version")) is int
             and configuration["schema_version"] == 3 and isinstance(defaults, dict))
    matches = valid and all(type(defaults.get(k)) is int and defaults[k] == v
                    for k, v in POC_DEFAULT_LIMITS.items())
    return {"target": dict(POC_DEFAULT_LIMITS), "stored": defaults if valid else None,
            "strict_match": bool(matches), "published_match": bool(matches and version == published_version),
            "version": version, "published_version": published_version,
            "inline_enforcement_verified": False, "completion_allowance": 1024,
            "completion_4096_verified": False}