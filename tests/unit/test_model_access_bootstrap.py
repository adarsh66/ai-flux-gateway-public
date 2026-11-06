"""Synthetic operator workflow, no credentials/network/PostgreSQL/DDL."""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from aiflux import model_access as access
from aiflux import model_access_bootstrap as boot
from aiflux.auth import Principal
from aiflux.models import CreditBudget, Member, ModelAccessPublication
from tests.unit.test_auto_shared_pricing import env
from tests.unit.test_model_access_publication import prepare

ROOT = Path(__file__).resolve().parents[2]
TARGET = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/test/providers/Microsoft.ApiManagement/service/test"


@pytest.fixture
def operator(env, monkeypatch):
    p = env
    oid, sid = prepare(p, monkeypatch)
    p.settings.model_access_enabled = False
    p.settings.apim_resource_id = TARGET
    p.settings.apim_product_id = "aiflux"
    inventory = [{"id": f"{TARGET}/subscriptions/{sid}", "name": sid,
                  "scope": f"{TARGET}/products/aiflux", "state": "active", "owner_id": None}]
    ownership = {sid: {"disposition": "bind", "organization_id": oid, "reason": "verified owner"}}
    monkeypatch.setattr(p.apim, "subscription_inventory", lambda: deepcopy(inventory), raising=False)
    monkeypatch.setattr(boot, "check_grants", lambda *_: {"dialect": "postgresql", "runtime_role": "runtime",
                          "tables": boot.TABLES, "least_privilege_verified": True})
    object_id = str(uuid4())
    p.db.add(Member(organization_id=oid, object_id=object_id, role="ids_admin", enabled=True))
    p.db.commit()
    return SimpleNamespace(p=p, oid=oid, sid=sid, inventory=inventory, ownership=ownership,
        principal=Principal(organization_id=oid, organization_name="org", tenant_id=str(uuid4()),
                    object_id=object_id, role="ids_admin"))


def review(o):
    return boot.preview(o.p.db, o.p.settings, o.p.apim, o.ownership, "runtime", ROOT)


def execute(o, reviewed):
    return boot.apply(o.p.db, o.p.settings, o.p.apim, o.principal, reviewed, "runtime", ROOT)


def test_complete_dryrun_review_import_publish_readback_receipt(operator):
    o = operator
    budget = CreditBudget(organization_id=o.oid, allowed_models_json="[]")
    o.p.db.add(budget)
    o.p.db.commit()
    money = budget.monthly_budget_usd
    before = access.preference(o.p.db, o.oid)
    reviewed = review(o)
    assert access.preference(o.p.db, o.oid) == before
    assert o.p.apim.puts == 0
    assert reviewed["legacy"][0]["denied_models"] == list("abcdef")
    receipt = execute(o, reviewed)
    assert boot.validate_receipt(receipt, ROOT, TARGET, "aiflux", list("abcdef"))
    assert not o.p.settings.model_access_enabled
    assert receipt["projection"]["organizations"][o.oid]["denied_models"] == list("abcdef")
    assert budget.monthly_budget_usd == money and budget.allowed_models_json == "[]"
    assert receipt["activation"] is False and o.p.apim.puts == 1


@pytest.mark.parametrize("change", ["unknown", "exclude_active", "wrong_org", "missing", "broad_scope", "other_product"])
def test_inventory_ownership_fails_closed(operator, change):
    o = operator
    if change == "unknown":
        o.inventory.append({**o.inventory[0], "name": "admin", "id": f"{TARGET}/subscriptions/admin"})
    elif change == "exclude_active":
        o.ownership[o.sid]["disposition"] = "exclude"
    elif change == "wrong_org":
        o.ownership[o.sid]["organization_id"] = str(uuid4())
    elif change == "missing":
        o.inventory.clear(); o.ownership.clear()
    elif change == "broad_scope":
        o.inventory[0]["scope"] = f"{TARGET}/apis"
        o.ownership[o.sid]["disposition"] = "exclude"
    else:
        o.inventory[0]["scope"] = f"{TARGET}/products/other"
        o.ownership[o.sid]["disposition"] = "exclude"
    with pytest.raises(ValueError):
        review(o)
    assert o.p.apim.puts == 0


def test_stale_review_and_failed_publication_never_emit_proof(operator):
    o = operator
    reviewed = review(o)
    o.inventory[0]["owner_id"] = "changed"
    with pytest.raises(ValueError, match="review changed"):
        execute(o, reviewed)
    assert access.preference(o.p.db, o.oid)["version"] == 0
    reviewed = review(o)
    o.p.apim.fault = "put"
    with pytest.raises(ValueError, match="publication pending"):
        execute(o, reviewed)
    assert o.p.db.get(ModelAccessPublication, "default").state == "error"


@pytest.mark.parametrize("change", ["source", "target", "catalog", "grant", "legacy", "etag", "stale", "digest"])
def test_receipt_mutations_rejected_even_when_resealed(operator, change):
    o = operator
    receipt = execute(o, review(o))
    if change == "source": receipt["source_sha256"] = {}
    elif change == "target": receipt["target"] += "-foreign"
    elif change == "catalog": receipt["projection"] = boot.seal({**{k: v for k, v in receipt["projection"].items() if k != "sha256"}, "catalog": []})
    elif change == "grant":
        receipt["after"]["grants"] = {}
        receipt["after"] = boot.seal({k: v for k, v in receipt["after"].items() if k != "sha256"})
    elif change == "legacy":
        receipt["review"]["legacy"][0]["review_sha256"] = "0" * 64
        receipt["review"] = boot.seal({k: v for k, v in receipt["review"].items() if k != "sha256"})
    elif change == "etag": receipt["etag"] = "*"
    elif change == "stale": receipt["observed_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    receipt = boot.seal({k: v for k, v in receipt.items() if k != "sha256"})
    if change == "digest": receipt["sha256"] = "0" * 64
    with pytest.raises((ValueError, KeyError)):
        boot.validate_receipt(receipt, ROOT, TARGET, "aiflux", list("abcdef"))


def test_sqlite_is_not_runtime_grant_proof(env):
    with pytest.raises(ValueError, match="PostgreSQL"):
        boot.check_grants(env.db, "runtime")


def test_unregistered_operator_cannot_self_assert_admin(operator):
    o = operator
    o.principal = Principal(o.oid, "org", str(uuid4()), str(uuid4()), "ids_admin")
    with pytest.raises(ValueError, match="administrator"):
        execute(o, review(o))
    assert o.p.apim.puts == 0


def test_legacy_import_failure_rolls_back_all_organizations(operator, monkeypatch):
    from aiflux.models import Organization
    o = operator
    other = str(uuid4())
    o.p.db.add(Organization(id=other, name="second", tenant_id=str(uuid4())))
    o.p.db.commit()
    reviewed = review(o)
    original = access.import_legacy
    calls = []
    def fail_second(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise ValueError("synthetic import failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(access, "import_legacy", fail_second)
    with pytest.raises(ValueError, match="synthetic"):
        execute(o, reviewed)
    o.p.db.expire_all()
    assert access.preference(o.p.db, o.oid)["version"] == 0
    assert access.preference(o.p.db, other)["version"] == 0
    assert o.p.apim.puts == 0


@pytest.mark.parametrize("fault", ["missing", "elevated", "schema", "owner", "extra", "absent"])
def test_postgresql_grant_observer_rejects_bad_effective_privileges(fault):
    class Rows:
        def mappings(self): return self
        def one(self): return {"rolsuper": fault == "elevated", "rolcreatedb": False, "rolcreaterole": False, "rolbypassrls": False}
    class Db:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        def execute(self, *_): return Rows()
        def scalar(self, stmt, params):
            sql = str(stmt)
            if "has_schema_privilege" in sql: return fault == "schema"
            if "pg_has_role" in sql: return None if fault == "absent" else fault == "owner"
            privilege = params["priv"]
            if fault == "missing" and privilege == "INSERT": return False
            if fault == "extra" and privilege == "DELETE": return True
            return privilege in boot.TABLES[params["table"].split(".")[1]]
    with pytest.raises(ValueError):
        boot.check_grants(Db(), "runtime")


def test_apim_inventory_pagination_strips_keys_and_rejects_foreign_continuation():
    import httpx
    from aiflux.apim import ApimClient, ApimError
    settings = SimpleNamespace(apim_resource_id=TARGET, apim_product_id="aiflux")
    client = ApimClient(settings)
    base = f"https://management.azure.com{TARGET}/subscriptions"
    urls = []
    def send(method, url):
        urls.append(url)
        assert method == "GET"
        return httpx.Response(200, json={"value": [{"id": f"{TARGET}/subscriptions/admin", "name": "admin",
            "properties": {"scope": f"{TARGET}/apis", "state": "active", "primaryKey": "NEVER-EXPORT"}}],
            "nextLink": "https://foreign.invalid/steal-token"})
    client._send = send
    with pytest.raises(ApimError): client.subscription_inventory()
    assert len(urls) == 1
    def paged(method, url):
        urls.append(url)
        assert method == "GET"
        if "skiptoken" in url: return httpx.Response(200, json={"value": []})
        return httpx.Response(200, json={"value": [{"id": f"{TARGET}/subscriptions/admin", "name": "admin",
            "properties": {"scope": f"{TARGET}/apis", "state": "active", "primaryKey": "NEVER-EXPORT"}}],
            "nextLink": base + "?api-version=2024-05-01&skiptoken=next"})
    client._send = paged
    rows = client.subscription_inventory()
    assert len(rows) == 1 and "NEVER-EXPORT" not in json.dumps(rows)


def test_terraform_external_protocol_validates_raw_pin_offline(operator, tmp_path, monkeypatch, capsys):
    import io
    import aiflux.config as config
    o = operator
    receipt = execute(o, review(o))
    path = tmp_path / "receipt.json"
    raw = access.compact(receipt).encode()
    path.write_bytes(raw)
    monkeypatch.setattr(config, "get_settings", lambda: pytest.fail("Terraform validator constructed settings"))
    query = {"receipt_path": str(path), "receipt_sha256": __import__("hashlib").sha256(raw).hexdigest(),
             "root": str(ROOT), "target": TARGET, "product": "aiflux", "aliases": json.dumps(list("abcdef"))}
    monkeypatch.setattr(boot.sys, "stdin", io.StringIO(json.dumps(query)))
    assert boot.main(["terraform-validate"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] == "true"
    query["receipt_sha256"] = "0" * 64
    monkeypatch.setattr(boot.sys, "stdin", io.StringIO(json.dumps(query)))
    assert boot.main(["terraform-validate"]) == 1


def test_offline_cli_validate_refuses_fake_receipt_before_settings(tmp_path, monkeypatch):
    import aiflux.config as config
    monkeypatch.setattr(config, "get_settings", lambda: pytest.fail("offline validation loaded credentials"))
    path = tmp_path / "fake.json"
    path.write_text(json.dumps({"sha256": "0" * 64}), encoding="utf-8")
    assert boot.main(["validate", "--root", str(ROOT), "--input", str(path), "--target", TARGET,
                      "--product", "aiflux", "--aliases", "[]"]) == 1