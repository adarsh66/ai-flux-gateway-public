"""Explicit operator workflow. Never invoked by startup, GET or migrations.

preview is read-only. apply imports reviewed restrictions, queues and publishes
with enforcement OFF, then emits a receipt ONLY after trusted readback. No DDL,
GRANT, key retrieval, provider calls, subscription creation or policy activation.
CLI errors are fixed strings: never print DSNs, ARM bodies or credentials.
"""
import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from aiflux import model_access as access
from aiflux.models import CreditBudget, GatewaySettings, Member, ModelAccessPublication, Organization, OrganizationModelAccess, TeamSubscription

TABLES = {
    "organization_model_access": ["SELECT", "INSERT", "UPDATE"],
    "organization_model_access_revisions": ["SELECT", "INSERT"],
    "model_access_publication": ["SELECT", "INSERT", "UPDATE"],
}
SOURCES = [
    "gateway/policies/model-access.xml.tftpl", "gateway/policies/auto-resolve.xml.tftpl",
    "services/control-plane/src/aiflux/model_access.py",
    "services/control-plane/src/aiflux/model_access_publisher.py",
    "services/control-plane/src/aiflux/model_access_bootstrap.py",
    "services/control-plane/src/aiflux/apim.py",
    "services/control-plane/src/aiflux/auto_pricing_worker.py",
    "services/control-plane/src/aiflux/settings_envelope.py",
    "services/control-plane/src/aiflux/gateway_settings.py",
    "services/control-plane/src/aiflux/turnstile_exchange.py",
    "services/control-plane/src/aiflux/external_inventory.py",
    "services/control-plane/migrations/versions/0005_organization_model_access.py",
    "infra/project-route/model-access.tf", "infra/project-route/main.tf",
]


def digest(value):
    return hashlib.sha256(access.compact(value).encode()).hexdigest()


def seal(value):
    return {**value, "sha256": digest(value)}


def verified(value):
    if not isinstance(value, dict) or value.get("sha256") != digest({k: v for k, v in value.items() if k != "sha256"}):
        raise ValueError("Invalid artifact digest")
    return value


def source_hashes(root):
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in SOURCES}


def check_grants(db, runtime_role):
    """Observe effective PostgreSQL runtime DML, not default-privilege guesses.

    Refuse superusers, role/DB creators, table/schema owners and effective
    DELETE/TRUNCATE/REFERENCES/TRIGGER or schema CREATE privileges. Never grant.
    """
    if db.bind.dialect.name != "postgresql" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", runtime_role):
        raise ValueError("PostgreSQL runtime role required")
    role = db.execute(text("SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls FROM pg_roles WHERE rolname=:role"),
                      {"role": runtime_role}).mappings().one()
    if any(role.values()):
        raise ValueError("Runtime role is elevated")
    if db.scalar(text("SELECT has_schema_privilege(:role, 'public', 'CREATE')"), {"role": runtime_role}):
        raise ValueError("Runtime schema CREATE is forbidden")
    result = {}
    for table, required in TABLES.items():
        owner = db.scalar(text("SELECT pg_has_role(:role, c.relowner, 'USAGE') FROM pg_class c "
                               "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=:table"),
                          {"role": runtime_role, "table": table})
        if owner is not False:
            raise ValueError("New table missing or runtime-owned")
        observed = [priv for priv in ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]
                    if db.scalar(text("SELECT has_table_privilege(:role, :table, :priv)"),
                                 {"role": runtime_role, "table": f"public.{table}", "priv": priv})]
        if observed != required:
            raise ValueError("New-table runtime privileges differ from least privilege")
        result[table] = observed
    return {"dialect": "postgresql", "runtime_role": runtime_role, "tables": result,
            "least_privilege_verified": True}


def operator_principal(db, object_id):
    """Resolve enabled admin membership, never turn a supplied UUID into a role.

    The process's separately authenticated DB/ARM credentials authorize actual
    operations; this membership is the audited application operator identity.
    """
    from aiflux.auth import Principal
    from uuid import UUID
    if str(UUID(object_id)) != object_id:
        raise ValueError("Canonical operator identity required")
    rows = db.execute(select(Member, Organization).join(Organization, Member.organization_id == Organization.id).where(
        Member.object_id == object_id, Member.role == "ids_admin", Member.enabled.is_(True),
        Organization.enabled.is_(True))).all()
    if len(rows) != 1:
        raise ValueError("Unambiguous enabled administrator required")
    member, org = rows[0]
    return Principal(organization_id=org.id, organization_name=org.name, tenant_id=org.tenant_id,
                     object_id=object_id, role="ids_admin")


def inventory_ownership(db, settings, inventory, ownership):
    """Every service subscription needs an explicit reviewed disposition.

    All active/in-transition subscriptions able to reach this product (including
    service/API/admin/dev keys) MUST have a canonical existing DB binding. No
    exclusion permits an active bypass. Only non-executable keys may be
    explicitly excluded; other-product active keys need separate remediation,
    not an assumption about product/API bindings. Partial inventories fail closed.
    """
    resource = settings.apim_resource_id.rstrip("/")
    product = f"{resource}/products/{settings.apim_product_id}"
    if not isinstance(ownership, dict) or len(inventory) != len(ownership):
        raise ValueError("Complete reviewed ownership required")
    rows = {s.id: s for s in db.scalars(select(TeamSubscription)).all()}
    bound, names = {}, set()
    for item in inventory:
        sid = item["name"]
        if sid in names or item["id"].lower() != f"{resource}/subscriptions/{sid}".lower():
            raise ValueError("Duplicate or foreign inventory item")
        names.add(sid)
        entry = ownership.get(sid, {})
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise ValueError("Ownership reason required")
        scope, state = item["scope"], item["state"]
        if not isinstance(scope, str) or not scope.lower().startswith(resource.lower() + "/"):
            raise ValueError("Unknown subscription scope")
        if state not in {"active", "suspended", "cancelled", "expired", "submitted", "rejected"}:
            raise ValueError("Unknown subscription state")
        relevant = scope.lower() == product.lower() or not scope.lower().startswith(resource.lower() + "/products/")
        executable = state in {"active", "submitted"}
        if entry.get("disposition") == "bind":
            sub = rows.get(sid)
            if (sub is None or entry.get("organization_id") != sub.organization_id
                    or sub.desired_state != "active" or sub.state not in {"active", "pending"}
                    or not executable or not relevant):
                raise ValueError("Inventory ownership does not match executable DB binding")
            bound[sid] = sub.organization_id
        elif entry.get("disposition") != "exclude" or executable:
            raise ValueError("Active admin/operator/dev or product key cannot be excluded")
    if set(ownership) != names:
        raise ValueError("Unknown ownership entries")
    expected = {s.id: s.organization_id for s in rows.values()
                if s.desired_state == "active" and s.state in {"active", "pending"}}
    if bound != expected:
        raise ValueError("Inventory missing executable database subscriptions")
    return bound


def preview(db, settings, apim, ownership, runtime_role, root):
    from aiflux.gateway_settings import fingerprint
    from aiflux.model_access_publisher import preflight
    inventory = apim.subscription_inventory()
    bindings = inventory_ownership(db, settings, inventory, ownership)
    models = access.catalog(db, settings)
    aliases = [m["id"] for m in models if m["model_kind"] == "chat"]
    enabled = [m["id"] for m in models if m["model_kind"] == "chat" and m["globally_enabled"]]
    legacy = [access.review_legacy(db, oid, aliases)
              for oid in db.scalars(select(Organization.id).order_by(Organization.id)).all()]
    projection = access.compile_projection(db, enabled)
    if projection["bindings"] != bindings:
        raise ValueError("Compiler binding differs from inventory")
    # Preview the actual post-import shape, including fragment capacity, rather
    # than claiming that a pre-import projection proves the migration fits.
    for review in legacy:
        pref = projection["organizations"][review["organization_id"]]
        if pref["version"] and (pref["denied_models"] != review["denied_models"] or pref["auto_enabled"] != review["auto_enabled"]):
            raise ValueError("Existing preferences disagree with legacy review")
        pref.update(version=pref["version"] or 1,
            denied_models=review["denied_models"], auto_enabled=review["auto_enabled"])
    projection = seal({k: v for k, v in projection.items() if k != "sha256"})
    preflight(db, projection)
    fragment, etag = apim.get_settings_fragment("dev-unified")
    return seal({"schema": 1, "kind": "model_access_bootstrap_preview", "target": settings.apim_resource_id,
                 "product": settings.apim_product_id, "inventory": inventory, "ownership": ownership,
                 "legacy": legacy, "preferences": {oid: access.preference(db, oid) for oid in projection["organizations"]},
                 "projection_preview": projection, "fragment_sha256": fingerprint(fragment), "etag": etag,
                 "grants": check_grants(db, runtime_role), "source_sha256": source_hashes(root)})


def apply(db, settings, apim, principal, reviewed, runtime_role, root):
    """Explicit future operator action. No network/DB action on receipt validation.

    Imports are one atomic transaction (save_access commits are suppressed via a
    nested session joined to an outer transaction). After that commit the durable
    outbox owns retry; failures emit no activation receipt. Re-preview after any
    ambiguous attempt; never silently reuse stale operator approval.
    """
    from aiflux.gateway_settings import fingerprint
    from aiflux.model_access_publisher import reconcile
    from aiflux.settings_envelope import parse
    access.admin(principal)
    if operator_principal(db, principal.object_id).organization_id != principal.organization_id:
        raise ValueError("Operator membership mismatch")
    if settings.model_access_enabled:
        raise ValueError("Bootstrap requires enforcement OFF")
    verified(reviewed)
    current = preview(db, settings, apim, reviewed["ownership"], runtime_role, root)
    if current != reviewed:
        raise ValueError("Bootstrap review changed; preview and review again")
    db.rollback()
    # Serialize publisher before importing; legacy rows/preferences are checked
    # again inside the write transaction, before any revision is committed.
    with db.begin():
        from aiflux.gateway_settings import locked_head
        head = locked_head(db, "dev-unified")
        if head is None:
            raise ValueError("Shared settings head missing")
        # Also begin the physical SQLite write transaction before SAVEPOINT.
        # Otherwise its legacy driver may release a top-level savepoint as a
        # commit; production PostgreSQL already holds this same row mutex.
        db.execute(update(GatewaySettings).where(GatewaySettings.scope == "dev-unified").values(version=head.version))
        # Stabilize existing reviewed source rows throughout the import. New
        # concurrent rows are also detected by post-publication re-observation;
        # they can never yield a stale activation receipt.
        for model in (Organization, TeamSubscription, OrganizationModelAccess, CreditBudget):
            db.scalars(select(model).with_for_update().execution_options(populate_existing=True)).all()
        current = preview(db, settings, apim, reviewed["ownership"], runtime_role, root)
        if current != reviewed:
            raise ValueError("Bootstrap review raced; review again")
        with Session(bind=db.connection(), join_transaction_mode="create_savepoint") as imports:
            for review in reviewed["legacy"]:
                oid = review["organization_id"]
                # Never overwrite previously managed preferences with legacy data.
                pref = access.preference(imports, oid)
                if pref["version"]:
                    if pref["denied_models"] != review["denied_models"] or pref["auto_enabled"] != review["auto_enabled"]:
                        raise ValueError("Existing preferences disagree with legacy review")
                    continue
                access.import_legacy(imports, settings, principal, oid, expected_version=0,
                    reviewed_sha256=review["review_sha256"], reason="Reviewed operator bootstrap")
            access.queue(imports)
            imports.commit()
    if not reconcile(db, settings, apim, immediate=True, bootstrap=True):
        raise ValueError("Bootstrap publication pending; no activation receipt")
    job = db.get(ModelAccessPublication, "default", populate_existing=True)
    fragment, etag = apim.get_settings_fragment("dev-unified")
    projection = parse(fragment)[2]
    if (not job or job.state != "applied" or job.generation != job.applied_generation
            or projection != json.loads(job.applied_json)):
        raise ValueError("Bootstrap readback mismatch")
    # Re-observe inventory/grants/legacy/catalog after remote publication. A
    # concurrent mutation invalidates this receipt, rather than inventing proof.
    after = preview(db, settings, apim, reviewed["ownership"], runtime_role, root)
    for key in ("inventory", "ownership", "legacy", "grants", "source_sha256"):
        if after[key] != reviewed[key]:
            raise ValueError("Bootstrap inputs changed during publication")
    latest = access.compile_projection(db, projection["catalog"], job.generation)
    if latest != projection or after["projection_preview"]["catalog"] != projection["catalog"]:
        raise ValueError("Bootstrap catalog/preferences changed")
    return seal({"schema": 1, "kind": "model_access_bootstrap_receipt", "target": settings.apim_resource_id,
                 "product": settings.apim_product_id, "observed_at": datetime.now(UTC).isoformat(),
                 "review": reviewed, "after": after, "projection": projection,
                 "fragment_sha256": fingerprint(fragment), "etag": etag,
                 "generation": job.generation, "operator_object_id": principal.object_id,
                 "source_sha256": source_hashes(root), "activation": False})


def validate_receipt(receipt, root, target, product, aliases, *, now=None):
    """Offline, fail-closed content/source binding, not a signature or live proof."""
    verified(receipt)
    review, after, projection = (verified(receipt[k]) for k in ("review", "after", "projection"))
    observed = datetime.fromisoformat(receipt["observed_at"])
    now = now or datetime.now(UTC)
    if observed.tzinfo is None or not timedelta(0) <= now - observed <= timedelta(hours=24):
        raise ValueError("Receipt is stale or future-dated")
    if (receipt["schema"] != 1 or receipt["kind"] != "model_access_bootstrap_receipt"
            or receipt["target"] != target or receipt["product"] != product or receipt["activation"] is not False
            or receipt["source_sha256"] != source_hashes(root)
            or projection["catalog"] != sorted(set(aliases)) or receipt["generation"] != projection["generation"]
            or projection["catalog_sha256"] != digest(sorted(set(aliases)))
            or not receipt["etag"] or receipt["etag"] == "*"
            or not re.fullmatch(r"[0-9a-f]{64}", receipt["fragment_sha256"])):
        raise ValueError("Receipt target, source, catalog or readback mismatch")
    for artifact in (review, after):
        if (artifact["target"] != target or artifact["product"] != product
                or artifact["source_sha256"] != receipt["source_sha256"]
                or artifact["grants"].get("dialect") != "postgresql"
                or artifact["grants"].get("least_privilege_verified") is not True
                or artifact["grants"].get("tables") != TABLES):
            raise ValueError("Receipt prerequisites missing")
    for key in ("inventory", "ownership", "legacy", "grants"):
        if after[key] != review[key]:
            raise ValueError("Receipt review changed")
    if after["fragment_sha256"] != receipt["fragment_sha256"] or after["etag"] != receipt["etag"]:
        raise ValueError("Receipt readback differs")
    expected_bindings = {sid: value["organization_id"] for sid, value in review["ownership"].items()
                         if value["disposition"] == "bind"}
    if projection["bindings"] != expected_bindings or len(review["inventory"]) != len(review["ownership"]):
        raise ValueError("Receipt inventory differs from projection")
    # Revalidate ownership content offline as well, not merely its hash. The
    # snapshot must account for admin/service/API/dev keys, never exempt them.
    names = set()
    resource = target.rstrip("/")
    product_scope = f"{resource}/products/{product}".lower()
    for item in review["inventory"]:
        sid = item["name"]
        entry = review["ownership"][sid]
        scope, state = item["scope"], item["state"]
        if (sid in names or item["id"].lower() != f"{resource}/subscriptions/{sid}".lower()
                or not scope.lower().startswith(resource.lower() + "/")
                or state not in {"active", "suspended", "cancelled", "expired", "submitted", "rejected"}
                or not entry["reason"].strip()):
            raise ValueError("Receipt inventory malformed")
        names.add(sid)
        relevant = scope.lower() == product_scope or not scope.lower().startswith(resource.lower() + "/products/")
        executable = state in {"active", "submitted"}
        if entry["disposition"] == "bind":
            from uuid import UUID
            if str(UUID(sid)) != sid or not relevant or not executable:
                raise ValueError("Receipt binding invalid")
        elif entry["disposition"] != "exclude" or executable:
            raise ValueError("Receipt exempts executable key")
    if names != set(review["ownership"]) or not receipt["operator_object_id"]:
        raise ValueError("Receipt ownership incomplete")
    after_projection = dict(after["projection_preview"])
    after_projection.pop("sha256")
    after_projection["generation"] = projection["generation"]
    if seal(after_projection) != projection:
        raise ValueError("Receipt post-import projection differs")
    for legacy in review["legacy"]:
        if legacy["review_sha256"] != digest({k: v for k, v in legacy.items() if k != "review_sha256"}):
            raise ValueError("Legacy review hash mismatch")
        pref = projection["organizations"][legacy["organization_id"]]
        if pref["denied_models"] != legacy["denied_models"] or pref["auto_enabled"] != legacy["auto_enabled"]:
            raise ValueError("Legacy import missing from projection")
    return True


def main(argv=None):
    # Terraform external protocol: local files only, no Settings/engine/client.
    if (argv if argv is not None else sys.argv[1:]) == ["terraform-validate"]:
        try:
            query = json.load(sys.stdin)
            raw = Path(query["receipt_path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != query["receipt_sha256"]:
                raise ValueError("Pinned receipt file differs")
            validate_receipt(json.loads(raw), Path(query["root"]), query["target"], query["product"],
                             json.loads(query["aliases"]))
            print(json.dumps({"valid": "true", "receipt_sha256": query["receipt_sha256"]}))
            return 0
        except Exception:
            print("Bootstrap receipt validation failed", file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preview", "apply", "validate"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True, help="Ownership JSON, reviewed preview, or receipt")
    parser.add_argument("--output", type=Path, help="Exclusive new output; never overwrite evidence")
    parser.add_argument("--runtime-role")
    parser.add_argument("--review-sha256")
    parser.add_argument("--operator-object-id")
    parser.add_argument("--target")
    parser.add_argument("--product")
    parser.add_argument("--aliases", help="JSON array for offline receipt validation")
    args = parser.parse_args(argv)
    try:
        value = json.loads(args.input.read_text(encoding="utf-8"))
        if args.action == "validate":
            validate_receipt(value, args.root, args.target, args.product, json.loads(args.aliases))
            print("Receipt content/source binding verified; not live or signed proof")
            return 0
        if args.output is None or args.output.exists() or not args.runtime_role:
            raise ValueError("Exclusive output and runtime role required")
        if args.action == "apply" and (args.review_sha256 != verified(value)["sha256"] or not args.operator_object_id):
            raise ValueError("Exact reviewed hash and operator identity required")
        # Deliberately lazy: offline validate cannot construct a credential or DB.
        from aiflux.apim import ApimClient
        from aiflux.config import get_settings
        from aiflux.db import engine_for
        settings = get_settings()
        with Session(engine_for(settings.database_url)) as db:
            if args.action == "preview":
                db.execute(text("SET TRANSACTION READ ONLY"))
                result = preview(db, settings, ApimClient(settings), value, args.runtime_role, args.root)
                db.rollback()
            else:
                principal = operator_principal(db, args.operator_object_id)
                result = apply(db, settings, ApimClient(settings), principal, value, args.runtime_role, args.root)
                validate_receipt(result, args.root, settings.apim_resource_id, settings.apim_product_id,
                                 result["projection"]["catalog"])
        with args.output.open("x", encoding="utf-8") as output:
            output.write(access.compact(result) + "\n")
        print("Bootstrap artifact written; enforcement remains OFF")
        return 0
    except Exception:
        print("Bootstrap refused or incomplete; no activation proof issued. Review inputs and durable outbox status.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())