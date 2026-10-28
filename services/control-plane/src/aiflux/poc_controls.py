"""Schema 3: optional overrides, never a gateway membership/authentication gate."""
import json
import xml.etree.ElementTree as ET
from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux.models import Organization, TeamSubscription
from aiflux.schemas import PocGatewayConfiguration, PocLimits, PocOverride, SafetyConfiguration


def effective(config: PocGatewayConfiguration, organization: str | None, subscription: str | None
              ) -> tuple[PocLimits, SafetyConfiguration]:
    limits, safety = config.defaults, config.safety
    for sub in (None, subscription):
        if sub is None and organization is None:
            continue
        for item in config.overrides:
            if str(item.organization_id) == organization and (
                str(item.subscription_id) if item.subscription_id else None
            ) == sub:
                limits, safety = item.limits or limits, item.safety or safety
        if subscription is None:
            break
    return limits, safety


def validate(db: Session, config: PocGatewayConfiguration) -> list[dict[str, str]]:
    rows = db.scalars(select(TeamSubscription).join(
        Organization, TeamSubscription.organization_id == Organization.id,
    ).where(Organization.enabled.is_(True)).order_by(TeamSubscription.id).limit(201)).all()
    if len(rows) > 200:
        raise HTTPException(422, "POC override ownership capacity is 200 subscriptions")
    bindings = [{"subscription_id": s.id, "organization_id": s.organization_id} for s in rows]
    owned = {(b["organization_id"], b["subscription_id"]) for b in bindings}
    seen = set()
    for item in config.overrides:
        key = (str(item.organization_id), str(item.subscription_id) if item.subscription_id else None)
        org = db.get(Organization, key[0])
        if key in seen or org is None or not org.enabled or (key[1] and key not in owned):
            raise HTTPException(422, "Duplicate, unavailable or foreign override target")
        seen.add(key)
    for safety in [config.safety, *(o.safety for o in config.overrides if o.safety)]:
        if not all((safety.prompt_attack, safety.input_filtering, safety.output_filtering)):
            raise HTTPException(422, "POC requires prompt shield and all input/output safety scans")
        if safety.protected_material:
            raise HTTPException(422, "Protected material detection is unavailable in this POC")
    return bindings


def render(config: PocGatewayConfiguration, bindings: Sequence[dict[str, str]]) -> str:
    """Resolve variables and execute one literal-call quota at the original position."""
    if len(bindings) > 200:
        raise HTTPException(422, "POC override ownership capacity is 200 subscriptions")
    root = ET.Element("fragment")

    def values(parent, limits=None, safety=None):
        if limits:
            for name in ("rpm", "tpm", "token_quota", "request_quota"):
                ET.SubElement(parent, "set-variable", name="aiflux-poc-" + name.replace("_", "-"),
                              value=f"@({getattr(limits, name)})")
        if safety:
            for name in ("hate", "violence", "sexual", "self_harm"):
                ET.SubElement(parent, "set-variable", name="aiflux-" + name.replace("_", "-") + "-threshold",
                              value=f"@({getattr(safety, name)})")

    values(root, config.defaults, config.safety)
    # Trusted ownership is compiled server-side. Unknown subscriptions retain
    # defaults; active exact-product authentication stays in the API envelope.
    mapping = {b["subscription_id"]: b["organization_id"] for b in bindings}
    encoded = json.dumps(mapping, separators=(",", ":")).replace('"', '""')
    ET.SubElement(root, "set-variable", name="aiflux-poc-organization", value=(
        '@{ var owners = JObject.Parse(@"' + encoded + '"); '
        'return (string)owners[context.Subscription.Id] ?? ""; }'))
    for subscription in (False, True):
        targets = [o for o in config.overrides if bool(o.subscription_id) == subscription]
        if not targets:
            continue
        choose = ET.SubElement(root, "choose")
        for item in sorted(targets, key=lambda o: (str(o.organization_id), str(o.subscription_id))):
            condition = f'@((string)context.Variables["aiflux-poc-organization"] == "{item.organization_id}"'
            if subscription:
                condition += f' && context.Subscription.Id == "{item.subscription_id}"'
            branch = ET.SubElement(choose, "when", condition=condition + ")")
            values(branch, item.limits, item.safety)
    # APIM quota-by-key.calls forbids expressions. Compile only configured
    # literal caps into mutually exclusive branches, retaining the SAME key,
    # window, epoch and one increment per request. Never scale increment-count.
    def quota(parent, calls):
        ET.SubElement(parent, "quota-by-key", calls=str(calls), **{
            "renewal-period": "86400",
            "counter-key": '@("project-demo:" + context.Subscription.Id)',
        })

    caps = sorted({config.defaults.request_quota, *(o.limits.request_quota for o in config.overrides if o.limits)} - {1000})
    if caps:
        choose = ET.SubElement(root, "choose")
        for cap in caps:
            branch = ET.SubElement(choose, "when", condition=(
                f'@((int)context.Variables["aiflux-poc-request-quota"] == {cap})'))
            quota(branch, cap)
        quota(ET.SubElement(choose, "otherwise"), 1000)
    else:
        quota(root, 1000)
    value = ET.tostring(root, encoding="unicode")
    if len(value.encode("utf-8")) > 65536:
        raise HTTPException(422, "POC settings exceed the supported 64KiB policy capacity")
    return value


def safety_patch(config: PocGatewayConfiguration, organization, subscription, safety, inherit):
    if subscription and not organization:
        raise HTTPException(422, "A subscription target requires its organization")
    if organization is None:
        if inherit:
            raise HTTPException(422, "Global defaults cannot inherit")
        return config.model_copy(update={"safety": safety})
    items = list(config.overrides)
    match = next((o for o in items if o.organization_id == organization
                  and o.subscription_id == subscription), None)
    if match:
        items.remove(match)
    updated = (match or PocOverride(organization_id=organization, subscription_id=subscription)).model_copy(
        update={"safety": None if inherit else safety})
    if updated.limits or updated.safety:
        items.append(updated)
    return config.model_copy(update={"overrides": items})