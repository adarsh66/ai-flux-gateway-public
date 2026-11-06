"""Private r5 inventory projection. Import is offline; no global transport patch."""
from contextlib import contextmanager
from copy import deepcopy
from html import unescape
from urllib.parse import unquote, urlsplit, parse_qsl

from scripts.deployment import auto_path_oct30_successor_r4 as r4
from scripts.deployment import poc_publisher_recheck_oct29 as product_reads
from scripts.deployment import project_route_product_access as product
from scripts.deployment import inventory_persistence_apply_once as inventory

d, tools = r4.d, r4.tools
ROOT = d.ROOT
RUNTIME = r4._copy(d.r.rt, ENV=dict(d.r.rt.ENV))
EVIDENCE = ROOT / ".deployment/oct30-r4-deployment-metadata-readonly-20261030T083951055335Z"
COMPARISON_SHA = "944559078fac9ac82edc5759f00cf2a3e327b7a8519fd9cf336194cd19b31f80"
ANALYSIS_SHA = "518fe92c1a0e32e68f5be6889b484b99211f8a3776382b8bd4a7b83973b45dd5"
HISTORICAL_SHA = "db638c31ca024ad815b9e9e2e0b6219b6c098e834dacc485b7752020e5cb0fb3"
ACCOUNT = d.r.rt.RG + "/providers/Microsoft.CognitiveServices/accounts/poc-ids-token-ex-foundry"
URL = "https://management.azure.com" + ACCOUNT + "/deployments?api-version=2025-06-01"
ADDED = frozenset(("Mistral-Large-3", "claude-haiku-5-5", "claude-opus-4-8",
    "claude-opus-5-5", "claude-opus-5-5-fast", "claude-sonnet-5-5",
    "gpt-6-luna", "gpt-6.1-terra", "mistral-medium-3-5"))
PROTECTED = frozenset(("Decision-1", "DeepSeek-V4-Flash", "DeepSeek-V4-Pro",
    "FW-GLM-5.3", "FW-MiniMax-M3", "Kimi-K2.7-Code", "gpt-4o", "gpt-5.4-mini",
    "gpt-5.6-luna", "gpt-6.1-sol", "grok-4-1-fast-reasoning", "grok-4-20-reasoning", "grok-4.3"))
REFERENCE_FILES = ("gateway/catalog/project-routes.json",
    "gateway/catalog/foundry-inventory-20261026.json")


def evidence():
    checked = r4.r3.checked_file
    checked(EVIDENCE, "deployment-comparison.json", COMPARISON_SHA)
    checked(EVIDENCE, "analysis.md", ANALYSIS_SHA)
    comparison = d.load(EVIDENCE / "deployment-comparison.json")
    path = checked(ROOT, comparison["historical_source"], comparison["historical_source_sha256"])
    historical = d.load(path)["foundry"]["deployments"]
    d.require(comparison["complete"] is True and comparison["removed"] == []
        and comparison["changed_existing"] == {} and set(comparison["added"]) == ADDED
        and comparison["account_resource_id"] == ACCOUNT
        and d.r.fs.sha(historical) == comparison["historical_collection_sha256"] == HISTORICAL_SHA,
        "r5_authenticated_old_full_collection")
    frozen = ROOT / comparison["last_successful_frozen_capture"]
    checked(ROOT, frozen.relative_to(ROOT), comparison["frozen_capture_sha256"])
    d.require(d.load(frozen)["baseline"]["model_metadata_sha256"] == HISTORICAL_SHA,
              "r5_old_collection_matches_actual_frozen_hash")
    d.require(set(index(historical["value"])) == PROTECTED, "r5_exact_original13_identities")
    return historical, comparison


def index(rows):
    d.require(isinstance(rows, list), "r5_collection_rows")
    result, identities = {}, set()
    for row in rows:
        d.require(isinstance(row, dict) and isinstance(row.get("name"), str), "r5_metadata_shape")
        name, rid = row["name"], row.get("id")
        d.require(rid == ACCOUNT + "/deployments/" + name
            and name not in result and rid.casefold() not in identities,
            "r5_foreign_or_duplicate_identity")
        result[name] = row
        identities.add(rid.casefold())
    return result


def projected(row):
    """Exactly the saved diagnostic projection, including ETag and all SKU fields."""
    props, system = row["properties"], row.get("systemData", {})
    return {"id": row["id"], "name": row["name"], "etag": row.get("etag"),
        "sku": deepcopy(row.get("sku")), "createdAt": system.get("createdAt"),
        "lastModifiedAt": system.get("lastModifiedAt"),
        **{key: deepcopy(props.get(key)) for key in ("model", "currentCapacity", "raiPolicyName",
            "provisioningState", "deploymentState", "capabilities", "versionUpgradeOption", "rateLimits")}}


def absent_references(value):
    # Conservative substring matching also rejects escaped/case-varied references.
    # No settings values/tokens are returned or persisted by this predicate.
    text = d.encode(value).decode().casefold()
    for _ in range(3):
        text = unescape(unquote(text))
    d.require(not any(name.casefold() in text for name in ADDED), "r5_added_deployment_referenced")


def complete_collection(fetch):
    """Fetch every page once, rejecting foreign links, loops, overflow and partials.

    fetch is the private strict bounded GET transport, never an SDK paginator.
    Retain full page envelopes separately; never hide an unknown envelope field.
    """
    pages, rows, visited, url = [], [], set(), URL
    for _ in range(16):
        parsed = urlsplit(url)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        d.require(parsed.scheme == "https" and parsed.netloc == "management.azure.com"
            and parsed.path == ACCOUNT + "/deployments" and not parsed.fragment
            and sum(k == "api-version" for k, _ in query) == 1
            and ("api-version", "2025-06-01") in query
            and all(k in {"api-version", "$skiptoken", "skiptoken"} for k, _ in query)
            and len({k for k, _ in query}) == len(query) and url not in visited,
            "r5_pagination_scope_or_cycle")
        visited.add(url)
        page = fetch(url)
        d.require(isinstance(page, dict) and isinstance(page.get("value"), list)
            and not any(k in page for k in ("error", "partial", "partialError", "@odata.nextLink")),
            "r5_partial_collection_rejected")
        # A collection envelope's only accepted fields are value and nextLink.
        d.require(set(page) <= {"value", "nextLink"}, "r5_unknown_collection_envelope")
        pages.append(deepcopy(page))
        rows.extend(page["value"])
        d.require(len(rows) <= 128 and sum(len(d.encode(p)) for p in pages) <= 8 * 1024 * 1024,
                  "r5_collection_bound")
        link = page.get("nextLink")
        d.require(link is None or isinstance(link, str), "r5_pagination_link_type")
        if not link:
            index(rows)
            return {"value": rows}, pages
        d.require(bool(page["value"]), "r5_empty_continuation_page")
        url = link
    raise RuntimeError("r5_incomplete_pagination_limit")


def protect(collection, pages, references, historical=None, comparison=None):
    if historical is None or comparison is None:
        historical, comparison = evidence()
    # Validate a retained complete page chain too, not just a caller's complete flag.
    iterator = iter(pages)
    rebuilt, checked_pages = complete_collection(lambda _: next(iterator))
    d.require(next(iterator, None) is None and rebuilt == collection, "r5_exact_complete_page_chain")
    actual, original = index(collection["value"]), index(historical["value"])
    d.require(set(original) == PROTECTED and set(actual) == PROTECTED | ADDED,
              "r5_exact_known_membership_no_future_additions_or_deletions")
    # Preserve the old collection's exact envelope and original ordering. No
    # deployment field is removed, defaulted, ignored, or replaced by a baseline.
    subset = deepcopy(historical)
    subset["value"] = [deepcopy(actual[row["name"]]) for row in historical["value"]]
    d.require(subset == historical and d.r.fs.sha(subset) == d.r.fs.sha(historical) == HISTORICAL_SHA,
              "r5_protected_full_metadata_hash_exact")
    expected = {row["name"]: row for row in comparison["current_deployments"]}
    additions = {name: deepcopy(actual[name]) for name in sorted(ADDED)}
    d.require(all(projected(row) == expected[name] for name, row in additions.items()),
              "r5_known_addition_metadata_changed")
    absent_references(references)
    account = {"value": [deepcopy(actual[name]) for name in sorted(actual)]}
    return subset, {"account": deepcopy(collection), "account_sha256": d.r.fs.sha(account),
        "pages": checked_pages, "pages_sha256": d.r.fs.sha(checked_pages),
        "additions": additions, "additions_sha256": d.r.fs.sha(additions),
        "protected_sha256": HISTORICAL_SHA, "protected_count": len(PROTECTED),
        "account_count": len(actual), "addition_names": sorted(ADDED),
        "comparison_sha256": COMPARISON_SHA, "references_sha256": d.r.fs.sha(references)}


class InventoryReads:
    """One collection read for each old consumer; consistent projection for both."""
    def __init__(self, fetch, references):
        self.fetch, self.references, self.observations = fetch, references, []

    def read(self):
        full, pages = complete_collection(self.fetch)
        subset, proof = protect(full, pages, self.references)
        if self.observations:
            d.require(proof["account_sha256"] == self.observations[0]["account_sha256"],
                      "r5_account_drift_during_capture")
        self.observations.append(proof)
        return subset


def private_controller(progress):
    """Clone only the existing read graph; no mutation of any imported module."""
    private = r4._copy(d)
    rt = r4._copy(RUNTIME, ENV=dict(RUNTIME.ENV))
    private.r = r4._copy(d.r, rt=rt)
    strict = r4.reads.TimedOpen(d.a.opener(rt.CA))

    def opened(request, **kwargs):
        return strict.open(request, timeout=kwargs.get("timeout", 90))

    backend = r4._copy(d.r.persistence.backend, rt=rt, urlopen=opened)
    fs = r4._copy(d.r.fs, rt=rt)
    portals = r4._copy(product.portals, rt=rt)
    native_cli = rt.cli

    def fetch(url):
        request = d.Request(url, headers={"Authorization": "Bearer " + backend.token("https://management.azure.com/")})
        with opened(request, timeout=90) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            d.require(response.status == 200 and len(raw) <= 8 * 1024 * 1024, "r5_bounded_successful_metadata")
            return d.json.loads(raw)

    reference_files = {name: (ROOT / name).read_bytes().decode() for name in REFERENCE_FILES}
    ledger = InventoryReads(fetch, reference_files)

    def cli(args):
        if args == ["rest", "--method", "get", "--url", URL]:
            return ledger.read()
        if args[:3] == ["rest", "--method", "get"] and len(args) == 5 and args[3] == "--url":
            url = args[4]
            d.require(url.startswith("https://management.azure.com/subscriptions/" + rt.SUB + "/")
                or url.startswith("https://management.azure.com/providers/Microsoft.Authorization/roleDefinitions/"),
                "r5_read_scope")
            return fetch(url)
        d.require(args[:2] in (["account", "show"], ["account", "get-access-token"])
            or args == ["role", "assignment", "list", "--subscription", rt.SUB, "--all", "--include-inherited"],
            "r5_only_existing_read_commands")
        return native_cli(args)

    rt.cli, rt.urlopen = cli, opened
    original_arm = rt.arm
    settings = {rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + name + "/config/appsettings/list"
                for name in ("api", "admin", "customer", "ingestion")}

    def arm(path, method="GET", *args, **kwargs):
        d.require(not args and not kwargs and (method == "GET" or (method == "POST" and path in settings)),
                  "r5_exact_existing_settings_reads")
        result = original_arm(path, method)
        if path in settings:
            absent_references(result)  # In memory ONLY, before original settings hashing.
        return result

    rt.arm = arm
    before_storage, approved_storage = r4.r3.old.storage_transition()
    historical_rt = r4._copy(rt)
    storage_calls = []

    def historical_cli(args):
        old_url = "https://management.azure.com" + backend.RID + "?api-version=2023-05-01"
        if args == ["rest", "--method", "get", "--url", old_url]:
            d.require(not storage_calls, "r5_single_storage_projection")
            actual = cli([*args[:-1], backend.URL])
            d.require(actual == approved_storage, "r5_exact_approved_whole_storage_account")
            projected_storage = deepcopy(actual)
            rules = projected_storage["properties"]["networkAcls"]["ipRules"]
            d.require(len(rules) == 5 and rules[-1] == {"value": r4.r3.old.IP, "action": "Allow"},
                      "r5_exact_storage_transition")
            rules.pop()
            d.require(projected_storage == before_storage, "r5_exact_old_storage_projection")
            storage_calls.append(True)
            return projected_storage
        return cli(args)

    historical_rt.cli = historical_cli
    protected = tools.bind(product.ProductRun.protected,
        {**vars(product), "rt": historical_rt, "fs": fs, "portals": portals})
    read_namespace = {**vars(product_reads), "rt": rt, "urlopen": opened, "READS": []}

    class ProductRun(product_reads.ReadOnlyProductRun):
        __init__ = tools.bind(product_reads.ReadOnlyProductRun.__init__, read_namespace)
        arm = tools.bind(product_reads.ReadOnlyProductRun.arm, read_namespace)

        def protected(self):
            result = protected(self)
            d.require(len(storage_calls) == 1, "r5_storage_projection_required")
            result["state_network"] = r4.r3.old.state_network(approved_storage)
            return result

        def policy(self):
            result = super().policy()
            absent_references(result)
            return result

    release = r4._copy(d.r.persistence.release, rt=rt, fs=fs, ProductRun=ProductRun)
    private.r.persistence = r4._copy(d.r.persistence, rt=rt, fs=fs, backend=backend, release=release)
    private.r.fs = fs
    private.r.login = r4._copy(d.r.login, rt=rt)
    supplemental_r = r4._copy(inventory.r, rt=rt, fs=fs)
    private.r.supplemental = tools.bind(inventory.supplemental, {**vars(inventory), "r": supplemental_r})
    private.a = r4._copy(d.a)
    private.a.opener = lambda ca: r4.reads.TimedOpen(d.a.opener(ca))
    private.c = r4._copy(d.c)

    class Reads(d.c.Reads):
        def __init__(self):
            self.token = backend.token("https://management.azure.com/")
            self.http = strict

    private.c.Reads = Reads

    @contextmanager
    def transport():
        progress["phase"] = "STRICT_READ_CONTEXT"
        yield  # All functions already close over PRIVATE namespaces.

    private.read_transport = transport
    return private, ledger


def collect(progress=None):
    private, ledger = private_controller({} if progress is None else progress)
    capture = private.collect()
    ledger.read()  # Independent closing full-account collection, no projection-only check.
    d.require(len(ledger.observations) == 3, "r5_snapshot_supplement_closing_three_reads")
    references = {"formats": capture["formats"], "inheritance": capture["inheritance"],
        "owned_api": capture["owned_api"], "baseline": capture["baseline"],
        "source_snapshots": ledger.references}
    absent_references(references)
    capture["account_inventory_r5"] = {"observations": ledger.observations,
        "references_sha256": d.r.fs.sha(references), "complete": True}
    return capture


retain_prepare_failure = r4.reads.retain_prepare_failure