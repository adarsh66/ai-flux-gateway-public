"""Execute the ACTUAL gateway price expression; offline, not APIM proof."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    dotnet = shutil.which("dotnet")
    assert dotnet, "Installed native SDK required; do not install or bypass policy"
    sdkline = subprocess.run([dotnet, "--list-sdks"], capture_output=True, text=True, check=True).stdout.splitlines()[-1]
    version, parent = sdkline.split(" ", 1)
    sdk = Path(parent.strip("[]")) / version
    packs = Path(dotnet).parent / "packs/Microsoft.NETCore.App.Ref"
    refs_path = sorted(packs.glob("*/ref/net*"))[-1]
    framework = refs_path.name
    runtime_version = refs_path.parent.parent.name
    folder = tmp_path_factory.mktemp("auto-price-native")
    template = (ROOT / "gateway/policies/auto-resolve.xml.tftpl").read_text()
    tree = ET.fromstring("<fragment>" + template + "</fragment>")
    nodes = tree.findall('.//set-variable[@name="aiflux-auto-snapshot"]')
    assert len(nodes) == 2
    expression = nodes[1].get("value")
    assert expression.startswith("@{")
    source = r'''
using System;
using System.Linq;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
public class Context { public Dictionary<string, object> Variables = new Dictionary<string, object>(); }
public static class Extensions {
 public static T GetValueOrDefault<T>(this Dictionary<string, object> values, string key, T fallback) {
  object value; return values.TryGetValue(key, out value) ? (T)value : fallback;
 }
}
public class Runner {
 Context context = new Context();
 public JObject Execute(JObject input) {
  context.Variables["aiflux-auto-snapshot"] = input["snapshot"].ToString(Formatting.None);
  context.Variables["aiflux-auto-price-projection"] = (string)input["raw"];
  return JObject.Parse(Merge());
 }
 string Merge() EXPRESSION
}
public class Program {
 public static void Main() {
    Console.InputEncoding = System.Text.Encoding.UTF8;
    Console.OutputEncoding = System.Text.Encoding.UTF8;
  var output = new JObject();
  foreach (var item in JObject.Parse(Console.In.ReadToEnd()).Properties()) {
    var culture = (string)item.Value["culture"] ?? "en-US";
    System.Globalization.CultureInfo.CurrentCulture = System.Globalization.CultureInfo.GetCultureInfo(culture);
   output[item.Name] = new Runner().Execute((JObject)item.Value);
  }
  Console.WriteLine(output.ToString(Formatting.None));
 }
}
'''.replace("EXPRESSION", expression[1:])
    (folder / "Harness.cs").write_text(source, encoding="utf-8")
    shutil.copyfile(sdk / "Newtonsoft.Json.dll", folder / "Newtonsoft.Json.dll")
    (folder / "Harness.runtimeconfig.json").write_text(json.dumps({"runtimeOptions": {
        "tfm": framework, "framework": {"name": "Microsoft.NETCore.App", "version": runtime_version}}}))
    refs = list(refs_path.glob("*.dll")) + [folder / "Newtonsoft.Json.dll"]
    args = ["-nologo", "-langversion:7.3", "-target:exe", '-out:"' + str(folder / "Harness.dll") + '"']
    args += ['-r:"' + str(p) + '"' for p in refs]
    args += ['"' + str(folder / "Harness.cs") + '"']
    (folder / "compile.rsp").write_text("\n".join(args))
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    built = subprocess.run([dotnet, str(sdk / "Roslyn/bincore/csc.dll"), "@" + str(folder / "compile.rsp")],
                           capture_output=True, text=True, timeout=60, env=env)
    assert built.returncode == 0, built.stdout + built.stderr
    pool = ["a", "b", "c", "d", "e", "f"]
    snapshot = {"version": "a" * 64, "candidates": {x: {"price": {"input": "1", "output": "2", "revision": "frozen", "manifest_sha256": "b" * 64}} for x in pool},
                "profiles": {x: {"candidate_models": pool, "instructions": "suitability"} for x in ("balanced", "cost", "quality")}}
    base = {"schema": 1, "pool_version": snapshot["version"], "rate_card_version": 1,
            "revision": "rate-card-v1", "source": "rate-card", "prices": {
                x: {"input": "0", "output": "2", "status": "configured", "revision": "row-v1",
                    "source_url": "", "source_model": "", "currency": "USD", "unit": "per_million_tokens"} for x in pool}}
    def signed(value):
        p = copy.deepcopy(value)
        compact = lambda v: json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        p["sha256"] = hashlib.sha256(compact(p).encode()).hexdigest()
        return compact(p)
    fixtures = {"known": {"snapshot": snapshot, "raw": signed(base)},
                "empty": {"snapshot": snapshot, "raw": ""},
                "oversize": {"snapshot": snapshot, "raw": "x" * 24577}}
    for name, count in (("unknown", 0), ("one-known", 1), ("two-known", 2)):
        p = copy.deepcopy(base)
        for x in pool[count:]:
            p["prices"][x] = None
        fixtures[name] = {"snapshot": snapshot, "raw": signed(p)}
    for name, change in (("bad-rate", "-1"), ("non-decimal", "1e1"), ("null-rate", None)):
        p = copy.deepcopy(base)
        p["prices"]["f"]["input"] = change
        fixtures[name] = {"snapshot": snapshot, "raw": signed(p)}
    for name, change in (("comma", "1,25"), ("huge", "9" * 4000),
                         ("unicode-digit", "١"), ("negative-zero", "-0"),
                         ("trailing-newline", "1\n"), ("plus", "+1")):
        p = copy.deepcopy(base)
        p["prices"]["f"]["input"] = change
        fixtures[name] = {"snapshot": snapshot, "raw": signed(p)}
    for culture in ("en-US", "fr-FR", "de-DE", "ar-SA"):
        for rate in ("0", "0.00000001", "99999.99999999", "100000", "000001.25000000"):
            p = copy.deepcopy(base)
            p["prices"]["a"]["input"] = rate
            fixtures[culture + ":" + rate] = {"snapshot": snapshot, "raw": signed(p), "culture": culture}
    p = copy.deepcopy(base)
    p["pool_version"] = "b" * 64
    fixtures["bad-pool"] = {"snapshot": snapshot, "raw": signed(p)}
    fixtures["tampered"] = {"snapshot": snapshot, "raw": signed(base).replace('"input":"0"', '"input":"9"')}
    # Canonical hash must not depend on transport key order, whitespace, or
    # literal vs escaped Unicode. Include Python ensure_ascii DEL boundary.
    p = copy.deepcopy(base)
    p["revision"] = "quoted \" \\ / \b\t\n\f\r \u007f é 中 😀"
    p["prices"]["a"]["source_model"] = p["revision"]
    fixtures["unicode"] = {"snapshot": snapshot, "raw": signed(p)}
    date_price = copy.deepcopy(base)
    date_price["revision"] = "2026-11-01T00:00:00Z"
    date_price["prices"]["a"]["source_model"] = "2026-11-01T00:00:00Z"
    fixtures["date-string"] = {"snapshot": snapshot, "raw": signed(date_price)}
    signed_p = json.loads(signed(p))
    reversed_p = {k: signed_p[k] for k in reversed(list(signed_p))}
    reversed_p["prices"] = {k: {f: v[f] for f in reversed(list(v))} for k, v in reversed(list(signed_p["prices"].items()))}
    fixtures["reordered"] = {"snapshot": snapshot, "raw": json.dumps(reversed_p, ensure_ascii=False, indent=2)}
    for name, field, value in (("schema-string", "schema", "1"), ("schema-bool", "schema", True),
                               ("version-string", "rate_card_version", "1"), ("version-negative", "rate_card_version", -1),
                               ("version-float", "rate_card_version", 1.0), ("source-mismatch", "source", "packaged-default"),
                               ("revision-empty", "revision", ""), ("revision-long", "revision", "x" * 2049),
                               ("extra-envelope", "instructions", "attacker")):
        p = copy.deepcopy(base)
        p[field] = value
        fixtures[name] = {"snapshot": snapshot, "raw": signed(p)}
    for name, field, value in (("status-unknown", "status", "unknown"), ("status-number", "status", 1),
                               ("currency-number", "currency", 1), ("bad-unit", "unit", "per_token"),
                               ("provenance-number", "source_model", 7), ("provenance-long", "source_url", "x" * 2049),
                               ("extra-row", "capabilities", ["scoring"]), ("precision", "input", "0.000000001"),
                               ("rate-limit", "input", "100000.00000001"), ("cached-null", "cached", None),
                               ("write-negative", "write", "-1")):
        p = copy.deepcopy(base)
        p["prices"]["f"][field] = value
        fixtures[name] = {"snapshot": snapshot, "raw": signed(p)}
    for name, alias in (("scorer", "Decision-1"), ("alias-substitution", "evil")):
        p = copy.deepcopy(base)
        p["prices"][alias] = p["prices"].pop("f")
        fixtures[name] = {"snapshot": snapshot, "raw": signed(p)}
    p = copy.deepcopy(base)
    del p["prices"]["f"]["source_url"]
    fixtures["missing-provenance"] = {"snapshot": snapshot, "raw": signed(p)}
    for status in ("public_list", "sourced_proxy", "tbc", "platform_default"):
        p = copy.deepcopy(base)
        p["prices"]["a"]["status"] = status
        p["prices"]["a"]["cached"] = "0"
        p["prices"]["a"]["write"] = "100000"
        fixtures[status] = {"snapshot": snapshot, "raw": signed(p)}
    p = copy.deepcopy(base)
    p["rate_card_version"] = 0
    p["source"] = "packaged-default"
    fixtures["published-default"] = {"snapshot": snapshot, "raw": signed(p)}
    run = subprocess.run([dotnet, str(folder / "Harness.dll")], input=json.dumps(fixtures),
                         capture_output=True, text=True, encoding="utf-8", timeout=60, env=env)
    assert run.returncode == 0, run.stderr
    return json.loads(run.stdout)


def test_actual_merge_hash_zero_and_profile_preservation(native):
    p = native["known"]
    assert p["candidates"]["a"]["price"]["input"] == "0"
    assert p["pricing_revision"] == "rate-card-v1"
    assert not p["cost_suitability_fallback"]
    assert p["profiles"]["quality"]["instructions"] == "suitability"


@pytest.mark.parametrize("name", ["empty", "oversize", "bad-rate", "non-decimal", "null-rate", "bad-pool", "tampered",
    "schema-string", "schema-bool", "version-string", "version-negative", "version-float", "source-mismatch",
    "revision-empty", "revision-long", "extra-envelope", "status-unknown", "status-number", "currency-number",
    "bad-unit", "provenance-number", "provenance-long", "extra-row", "precision", "rate-limit", "cached-null",
    "write-negative", "scorer", "alias-substitution", "missing-provenance", "comma", "huge",
    "unicode-digit", "negative-zero", "trailing-newline", "plus"])
def test_actual_merge_invalid_atomic_defaults(native, name):
    p = native[name]
    assert p["pricing_source"] == "packaged-default"
    assert p["pricing_revision"] == "frozen"
    assert p["pricing_sha256"] == "b" * 64  # Manifest hash, NOT pool hash.
    assert all(c["price"]["input"] == "1" for c in p["candidates"].values())


@pytest.mark.parametrize("name", ["unknown", "one-known"])
def test_actual_unknown_cost_suitability_not_disabled(native, name):
    p = native[name]
    assert p["cost_suitability_fallback"]
    assert len(p["profiles"]["cost"]["candidate_models"]) == 6
    assert p["candidates"]["f"]["price"] is None
    assert "do not invent" in p["profiles"]["cost"]["instructions"]


def test_actual_known_comparable_cost_pool(native):
    assert native["two-known"]["profiles"]["cost"]["candidate_models"] == ["a", "b"]


@pytest.mark.parametrize("name", ["unicode", "reordered"])
def test_canonical_ascii_hash_independent_of_transport(native, name):
    assert native[name]["pricing_source"] == "rate-card"
    assert "😀" in native[name]["pricing_revision"]
    assert native[name]["pricing_stale"] is None


@pytest.mark.parametrize("status,origin", [("public_list", "published"), ("sourced_proxy", "provisional"),
    ("tbc", "provisional"), ("platform_default", "provisional"), ("known", "configured")])
def test_dynamic_price_origin_not_static_and_optional_zero(native, status, origin):
    assert native[status]["candidates"]["a"]["price_status"] == origin
    if status != "known":
        assert native[status]["candidates"]["a"]["price"]["cached"] == "0"


def test_published_default_envelope_is_valid(native):
    assert native["published-default"]["candidates"]["a"]["price"]["input"] == "0"
    assert native["published-default"]["pricing_revision"] == "rate-card-v1"


def test_provenance_date_shape_remains_a_string_not_newtonsoft_date(native):
    assert native["date-string"]["pricing_source"] == "rate-card"


@pytest.mark.parametrize("culture", ["en-US", "fr-FR", "de-DE", "ar-SA"])
@pytest.mark.parametrize("rate", ["0", "0.00000001", "99999.99999999", "100000", "000001.25000000"])
def test_bounded_ascii_decimal_culture_independent_source_strings(native, culture, rate):
    value = native[culture + ":" + rate]
    assert value["pricing_source"] == "rate-card"
    assert value["candidates"]["a"]["price"]["input"] == rate


def test_pricing_expression_uses_only_permitted_types():
    template = (ROOT / "gateway/policies/auto-resolve.xml.tftpl").read_text()
    for forbidden in ("System.Globalization", "JsonSerializerSettings", "DateParseHandling", "StringEscapeHandling"):
        assert forbidden not in template
    assert "decimal.TryParse" not in template and "decimal.Parse" not in template