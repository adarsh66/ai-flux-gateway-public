"""Adopt a reviewed platform pool transition through an ordinary audited Save.

This is not a drift bypass. The immutable release receipt, current published
snapshot, full predecessor and full successor fragment must all agree. Prices,
controls and sibling envelope data cannot change during adoption. The caller
holds the shared-head lock and writes only the NEW append-only revision.
"""
from copy import deepcopy
import hashlib

from aiflux import auto_pricing, auto_snapshot, completion_limits
from aiflux.external_inventory import AcceptedInventory

# Reviewed 4096 release: COMPOSE receipt sha256 f4e6de6f78bf6d9637c939e1219d987
# 7981488ccb8912f6fea64349a19dc96b3. Future platform releases must add their own
# reviewed predecessor/successor receipt; arbitrary valid projections are NOT
# admitted. These are public integrity pins, never credentials.
REVIEWED_TRANSITIONS = ({
    "from_pool": "10359b8e7939683fa239c04eefb840a9e21080c1cfed0ac62631ba8ee554fe8e",
    "to_pool": "5f6d1b489403af83d635fbc4128a0a4389ca2d7e100c8ed620dbb3de1adc1e51",
    "policy_sha256": "7c2194b4599f7b117f23e0dc2b12bdfbf9e576a5e12c770cb899683e27a70bf1",
    "completion_contract_sha256": "02e6393b1e43b3eece85c651a930b3ff16c685f32f40095ed550dd35d6c4b5e2",
    "release_receipt_sha256": "f4e6de6f78bf6d9637c939e1219d9877981488ccb8912f6fea64349a19dc96b3",
},)


def adopt(settings, row, stored, baseline, current):
    """Return copied metadata + safe receipt, or None; never SQL/network writes.

    The full-fragment equality is checked AFTER reconstructing the one allowed
    transition, not by stripping fields from an untrusted remote projection.
    No mutation of the historical row or its nested JSON is permitted here.
    """
    from aiflux.gateway_settings import fingerprint
    if row.state != "published" or not auto_pricing.enabled(settings):
        return None
    try:
        applied = auto_pricing.validate_projection(stored["auto_pricing"]["applied"])
        snapshot = auto_snapshot.defaults(settings)
        publication = auto_snapshot.publication(settings, snapshot)
        if publication is None:
            return None
        aliases = {candidate["id"] for candidate in snapshot["candidates"]}
        contract = completion_limits.load(settings, AcceptedInventory.load(settings).accepted_aliases(settings))
        if contract is None or set(applied["prices"]) != aliases:
            return None
        reviewed = next((item for item in REVIEWED_TRANSITIONS
            if item["from_pool"] == applied["pool_version"]
            and item["to_pool"] == snapshot["version"]
            and item["policy_sha256"] == publication["policy_sha256"]
            and item["completion_contract_sha256"] == contract[1]), None)
        if reviewed is None:
            return None
        successor = deepcopy(applied)
        successor["pool_version"] = reviewed["to_pool"]
        successor["sha256"] = hashlib.sha256(auto_pricing.compact(
            {key: value for key, value in successor.items() if key != "sha256"}).encode()).hexdigest()
        auto_pricing.validate_projection(successor)
        # render_revision already envelopes a priced predecessor. Rebuild from
        # its strictly recognized controls, never nest the old price branch.
        target = auto_pricing.envelope(auto_pricing.controls_only(baseline), successor)
        target_hash = fingerprint(target)
        if fingerprint(current) != target_hash:
            return None
        receipt = {"schema": 1, **reviewed, "predecessor_version": row.version,
            "predecessor_fragment_sha256": fingerprint(baseline),
            "successor_fragment_sha256": target_hash,
            "predecessor_projection_sha256": applied["sha256"],
            "successor_projection_sha256": successor["sha256"]}
        metadata = deepcopy({key: value for key, value in stored.items()
                             if key not in {"configuration", "bindings"}})
        metadata["auto_pricing"]["applied"] = successor
        metadata["auto_pricing_pool_transition"] = receipt
        return metadata, receipt
    except (KeyError, TypeError, ValueError):
        return None