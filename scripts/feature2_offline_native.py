"""Local-only typed C# compilation of current templates. No historical runner.

Uses installed .NET/Roslyn/Newtonsoft only; no restore/network/provider calls.
Receipt is deliberately NOT APIM service acceptance or execution proof.
"""
import hashlib
import argparse
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / ".deployment/feature2-model-access-source-20261103-01/native02"


def main():
    global HOME
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", default="native02", choices=["native02", "native03"])
    args = parser.parse_args()
    HOME = HOME.parent / args.receipt
    HOME.mkdir(exist_ok=False)
    dotnet = Path("C:/Program Files/dotnet")
    sdk = dotnet / "sdk/10.0.303"
    roslyn = sdk / "Roslyn/bincore"
    refs = sorted((dotnet / "packs/Microsoft.NETCore.App.Ref").iterdir())[-1] / "ref/net10.0"
    runtime = sorted((dotnet / "shared/Microsoft.NETCore.App").iterdir())[-1]
    dll = HOME / "Feature2Native.dll"
    original = ROOT / "scripts/deployment/auto_resume06_native.cs"
    source = HOME / "Feature2Native.cs"
    # Extend the retained typed fixture for isolated expression execution only.
    # This never runs an APIM policy or calls its network/provider policies.
    harness = original.read_text().replace("return result.Success ? 0 : 1;", '''
        if (result.Success && args.Length > 4) {
            var assembly = System.Reflection.Assembly.Load(output.ToArray());
            var type = assembly.GetType("Expressions");
            var contextType = assembly.GetType("Context");
            var identityType = assembly.GetType("Identity");
            var instance = Activator.CreateInstance(type);
            using var cases = JsonDocument.Parse(File.ReadAllText(args[4]));
            foreach (var test in cases.RootElement.EnumerateArray()) {
                var context = Activator.CreateInstance(contextType);
                var variables = new System.Collections.Generic.Dictionary<string,object>();
                foreach (var entry in test.GetProperty("variables").EnumerateObject()) {
                    variables[entry.Name] = entry.Value.ValueKind == JsonValueKind.String
                        ? (object)entry.Value.GetString() : entry.Value.GetBoolean();
                }
                contextType.GetProperty("Variables").SetValue(context, variables);
                if (test.TryGetProperty("subscription", out var sid)) {
                    var identity = Activator.CreateInstance(identityType);
                    identityType.GetProperty("Id").SetValue(identity, sid.GetString());
                    contextType.GetProperty("Subscription").SetValue(context, identity);
                }
                var actual = type.GetMethod("F" + test.GetProperty("expression").GetInt32()).Invoke(instance, new[] { context });
                Console.WriteLine(JsonSerializer.Serialize(new { name = test.GetProperty("name").GetString(), actual }));
            }
        }
        return result.Success ? 0 : 1;''')
    source.write_text(harness)
    def run(name, args):
        value = subprocess.run([str(a) for a in args], capture_output=True, timeout=90)
        (HOME / f"{name}.stdout.txt").write_bytes(value.stdout)
        (HOME / f"{name}.stderr.txt").write_bytes(value.stderr)
        (HOME / f"{name}.json").write_text(json.dumps({"exit": value.returncode, "args": [str(a) for a in args]}))
        print(value.stdout.decode(errors="replace"), value.stderr.decode(errors="replace"))
        return value.returncode
    code = run("compiler", [dotnet / "dotnet.exe", roslyn / "csc.dll", "-nologo", "-target:exe", f"-out:{dll}",
        *[f"-r:{p}" for p in refs.glob("*.dll")],
        *[f"-r:{roslyn / n}" for n in ("Microsoft.CodeAnalysis.dll", "Microsoft.CodeAnalysis.CSharp.dll")], source])
    if code:
        raise SystemExit(code)
    for name in ("Microsoft.CodeAnalysis.dll", "Microsoft.CodeAnalysis.CSharp.dll"):
        (HOME / name).write_bytes((roslyn / name).read_bytes())
    (HOME / "Newtonsoft.Json.dll").write_bytes((sdk / "Newtonsoft.Json.dll").read_bytes())
    (HOME / "Feature2Native.runtimeconfig.json").write_text(json.dumps({"runtimeOptions": {
        "tfm": "net10.0", "framework": {"name": "Microsoft.NETCore.App", "version": runtime.name}}}))
    expressions = []
    sources = {}
    aliases = [f"model-{i:02}" for i in range(22)]
    substitutions = {"fragment": "aiflux-dev-unified-poc-settings", "aliases": ", ".join(json.dumps(a) for a in aliases),
        "pricing_fragment": "aiflux-dev-unified-poc-settings", "completion_limit": "1024",
        "candidate_conditions": "true", "manifest_conditions": "true", "selected_limit_rules": "modelMaximum = 1024;",
        "provider_rules": "", "selected_limits": "", "snapshot_base64": "e30=", "gateway_client": "00000000-0000-0000-0000-000000000001"}
    for name in ("model-access", "auto-resolve"):
        path = ROOT / f"gateway/policies/{name}.xml.tftpl"
        text = path.read_text()
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        text = re.sub(r"\$\{([^}]+)\}", lambda m: substitutions.get(m[1], "UNRESOLVED_" + m[1]), text)
        (HOME / f"{name}.xml").write_text("<fragment>" + text + "</fragment>")
        root = ET.fromstring("<fragment>" + text + "</fragment>")
        for node in root.iter():
            expressions.extend(v for v in node.attrib.values() if v.startswith("@"))
            if (node.text or "").startswith("@"):
                expressions.append(node.text)
    (HOME / "expressions.json").write_text(json.dumps(expressions))
    fixtures, expectations = [], {}
    def fixture(name, expression, variables, expected, subscription=None):
        item = {"name": name, "expression": expression, "variables": variables}
        if subscription is not None:
            item["subscription"] = subscription
        fixtures.append(item)
        expectations[name] = expected
    def compact(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    sid, oid = "00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"
    value = {"schema": 1, "generation": 1, "catalog": aliases,
             "catalog_sha256": hashlib.sha256(compact(aliases).encode()).hexdigest(),
             "bindings": {sid: oid}, "organizations": {oid: {"version": 1, "enabled": True,
                 "auto_enabled": True, "denied_models": []}}}
    value["sha256"] = hashlib.sha256(compact(value).encode()).hexdigest()
    projection_index = next(i for i, e in enumerate(expressions) if "var projection = JObject.Parse(raw)" in e)
    deny_index = next(i for i, e in enumerate(expressions) if 'return !(bool)access["enabled"]' in e)
    fixture("valid-binding", projection_index, {"aiflux-model-access-projection": compact(value)},
            {"enabled": True, "auto_enabled": True, "allowed": aliases}, sid)
    fixture("unknown-binding", projection_index, {"aiflux-model-access-projection": compact(value)}, "", oid)
    fixture("malformed", projection_index, {"aiflux-model-access-projection": "{}"}, "", sid)
    tampered = {**value, "generation": 2}
    fixture("invalid-hash", projection_index, {"aiflux-model-access-projection": compact(tampered)}, "", sid)
    for alias in aliases:
        for allowed in ([], [alias]):
            fixture(f"explicit-{alias}-{'allow' if allowed else 'deny'}", deny_index,
                {"aiflux-model": alias, "aiflux-model-access": compact({"enabled": True, "auto_enabled": True, "allowed": allowed})}, not bool(allowed))
    fixture("auto-disabled", deny_index, {"aiflux-model": "auto", "aiflux-model-access": compact(
        {"enabled": True, "auto_enabled": False, "allowed": aliases})}, True)
    snapshot_index = next(i for i, e in enumerate(expressions) if "Entitlement intersection AFTER" in e)
    single_index = next(i for i, e in enumerate(expressions) if ".Properties().Single().Name" in e)
    final_index = next(i for i, e in enumerate(expressions) if 'return !string.IsNullOrEmpty(raw)' in e)
    pool = aliases[:6]
    snapshot = {"version": "v1", "candidates": {a: {"price": None, "max_completion_tokens": 1024} for a in pool},
                "profiles": {p: {"candidate_models": pool, "instructions": p} for p in ("balanced", "cost", "quality")}}
    for size in (0, 1, 6):
        variables = {"aiflux-auto-snapshot": compact(snapshot), "aiflux-model-access": compact({"allowed": pool[:size]})}
        # Structural assertions on these actual native results below.
        fixture(f"auto-intersection-{size}", snapshot_index, variables, {"candidate_count": size})
    single = {**snapshot, "candidates": {pool[0]: snapshot["candidates"][pool[0]]}, "pricing_revision": "v1",
              "pricing_sha256": "", "pricing_source": "packaged-default", "pricing_stale": None,
              "cost_suitability_fallback": True}
    fixture("auto-single-no-scoring", single_index, {"aiflux-auto-snapshot": compact(single),
        "aiflux-auto-profile": "balanced", "aiflux-request-json": compact({"max_completion_tokens": 1024})},
        {"selection_mode": "single-allowed-candidate"})
    fixture("auto-single-over-limit", single_index, {"aiflux-auto-snapshot": compact(single),
        "aiflux-auto-profile": "balanced", "aiflux-request-json": compact({"max_completion_tokens": 1025})}, "")
    fixture("final-selected-denied", final_index, {"aiflux-model": pool[0],
        "aiflux-model-access": compact({"allowed": []})}, True)
    (HOME / "fixtures.json").write_text(json.dumps(fixtures))
    code = run("semantic", [dotnet / "dotnet.exe", dll, "execute", HOME / "expressions.json", refs, sdk / "Newtonsoft.Json.dll", HOME / "fixtures.json"])
    executed = 0
    if not code:
        for line in (HOME / "semantic.stdout.txt").read_text().splitlines():
            result = json.loads(line)
            if "actual" not in result:
                continue
            actual, expected = result["actual"], expectations[result["name"]]
            if isinstance(actual, str) and actual:
                actual = json.loads(actual)
            if result["name"].startswith("auto-intersection-"):
                assert len(actual["candidates"]) == expected["candidate_count"]
                assert all(set(p["candidate_models"]) <= set(actual["candidates"]) for p in actual["profiles"].values())
            elif result["name"] == "auto-single-no-scoring":
                assert actual["selection_mode"] == expected["selection_mode"]
                assert actual["decision_overhead"]["usage"]["input_tokens"] is None
            else:
                assert actual == expected, result["name"]
            executed += 1
        assert executed == len(fixtures)
    (HOME / "source-binding.json").write_text(json.dumps({"sources": sources, "expressions": len(expressions),
        "semantic_exit": code, "execution": executed, "service_acceptance": False,
        "limitation": "Synthetic aliases and binding substitutions; not full Terraform rendering, network policy execution or APIM acceptance."}, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()