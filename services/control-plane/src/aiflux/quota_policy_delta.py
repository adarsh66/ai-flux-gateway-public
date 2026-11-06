"""Exact raw-text inline quota delta; no XML round-trip or pricing consumer.

Output changes intentionally require a separate verified provider-cap contract.
This constructor never applies a policy, activates detached controls or rekeys.
"""


def inline_quota_delta(raw: str) -> str:
    replacements = {
        'calls="1000" renewal-period="86400"': 'calls="50000" renewal-period="86400"',
        'tokens-per-minute="2048" token-quota="10000" token-quota-period="Daily"':
            'tokens-per-minute="300000" token-quota="20000000" token-quota-period="Daily"',
    }
    # Active explicit + selected Auto model token nodes, one shared call node.
    expected = [1, 2]
    result = raw
    for (old, new), count in zip(replacements.items(), expected, strict=True):
        if result.count(old) != count:
            raise ValueError("Current inline policy contract differs; no quota delta")
        result = result.replace(old, new)
    restored = result
    for old, new in replacements.items():
        restored = restored.replace(new, old)
    if restored != raw:
        raise ValueError("Non-quota raw bytes changed")
    return result