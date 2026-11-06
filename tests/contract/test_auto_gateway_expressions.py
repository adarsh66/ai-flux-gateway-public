"""Execute rendered C# offline with minimal stubs. NOT APIM runtime proof."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import pytest

from test_auto_gateway_policy import ROOT, render


@pytest.fixture(scope="module")
def expressions(tmp_path_factory):
    dotnet = shutil.which("dotnet")
    if not dotnet:
        pytest.skip("Existing .NET SDK unavailable; no install or APIM compilation claimed")
    sdks = subprocess.run([dotnet, "--list-sdks"], capture_output=True, text=True, check=True).stdout.splitlines()
    version, directory = sdks[-1].split(" ", 1)
    major = int(version.split(".")[0])
    reference = Path(directory.strip("[]")) / version / "Newtonsoft.Json.dll"
    assert reference.is_file(), "Existing SDK Newtonsoft assembly required; no package download"
    rendered = render([f"-var=route_manifest_path={ROOT / 'gateway/catalog/fireworks-candidate-routes.json'}", "-var=glm_enabled=true"])
    tree = ET.fromstring(rendered["on"])
    merge = tree.findall('.//set-variable[@name="aiflux-auto-snapshot"]')[1].get("value")[1:]
    result = tree.find('.//set-variable[@name="aiflux-auto-result"]').get("value")[1:]
    wire = tree.find('.//send-request[@id="aiflux-auto-resolver"]/set-body').text[1:]
    metadata = tree.find('.//set-body[@id="aiflux-auto-metadata"]').text[1:]
    trace = tree.find('.//trace/metadata[@name="payload"]').get("value")[1:]
    folder = tmp_path_factory.mktemp("auto-csharp-offline")
    project = folder / "Harness.csproj"
    project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
        f'<TargetFramework>net{major}.0</TargetFramework><LangVersion>7.3</LangVersion>'
        '<RestoreIgnoreFailedSources>true</RestoreIgnoreFailedSources></PropertyGroup><ItemGroup>'
        f'<Reference Include="Newtonsoft.Json"><HintPath>{reference.as_posix()}</HintPath></Reference>'
        '</ItemGroup></Project>', encoding="utf-8")
    (folder / "Program.cs").write_text(r'''
using System;
using System.Linq;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
public class Body {
    public string Raw;
    public T As<T>(bool preserveContent) { return typeof(T) == typeof(string) ? (T)(object)Raw : JsonConvert.DeserializeObject<T>(Raw); }
}
public interface IResponse { int StatusCode { get; } Body Body { get; } }
public class Response : IResponse { public int StatusCode { get; set; } public Body Body { get; set; } }
public class Context { public Dictionary<string, object> Variables = new Dictionary<string, object>(); public IResponse Response; public Guid RequestId = Guid.NewGuid(); }
public static class Extensions {
    public static T GetValueOrDefault<T>(this Dictionary<string, object> values, string key, T fallback) {
        object value; return values.TryGetValue(key, out value) ? (T)value : fallback;
    }
}
public class Runner {
    private Context context = new Context();
    public JObject Execute(JObject fixture, string snapshot) {
        var profile = (string)fixture["profile"] ?? "balanced";
        var request = new JObject { ["model"] = "auto", ["max_completion_tokens"] = (int?)fixture["maximum"] ?? 20,
            ["messages"] = fixture["messages"] ?? new JArray(new JObject { ["role"] = "user", ["content"] = "REDACTED" }) };
        context.Variables["aiflux-auto-redacted"] = request.ToString();
        context.Variables["aiflux-request-json"] = request.ToString();
        context.Variables["aiflux-auto-profile"] = profile;
        context.Variables["aiflux-auto-snapshot"] = fixture["snapshot"] == null ? snapshot : fixture["snapshot"].ToString();
        context.Variables["aiflux-auto-price-projection"] = (string)fixture["pricing"] ?? "";
        context.Variables["aiflux-auto-snapshot"] = Merge();
        context.Variables["aiflux-auto-started"] = DateTime.UtcNow.Ticks - ((long?)fixture["elapsed"] ?? 10) * 10000;
        context.Variables["aiflux-auto-response"] = new Response { StatusCode = (int?)fixture["status"] ?? 200,
            Body = new Body { Raw = fixture["raw"] == null ? fixture["scoring"].ToString() : (string)fixture["raw"] } };
        var output = new JObject();
        try { output["wire"] = JObject.Parse(Wire()); } catch { output["wire_rejected"] = true; }
        var route = Result();
        output["rejected"] = route == "";
        if (route != "") {
            output["routing"] = JObject.Parse(route);
            context.Variables["aiflux-auto-result"] = route;
            output["trace"] = JObject.Parse(Trace());
            context.Response = new Response { StatusCode = 200, Body = new Body { Raw = "{\"model\":\"provider-actual-model\",\"usage\":{\"total_tokens\":7}}" } };
            output["completion"] = JObject.Parse(Metadata());
        }
        return output;
    }
    private string Result()
''' + result + '\n private string Merge()\n' + merge + '\n private string Wire()\n' + wire + '\n private string Metadata()\n' + metadata + '\n private string Trace()\n' + trace + r'''
}
public class Program {
    public static void Main() {
        var input = JObject.Parse(Console.In.ReadToEnd());
        var results = new JObject();
        foreach (var fixture in ((JObject)input["fixtures"]).Properties()) {
            results[fixture.Name] = new Runner().Execute((JObject)fixture.Value, (string)input["snapshot"]);
        }
        Console.WriteLine(results.ToString(Formatting.None));
    }
}
''', encoding="utf-8")
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
    build = subprocess.run([dotnet, "build", str(project), "--verbosity", "quiet"],
        capture_output=True, text=True, env=env, timeout=180)
    assert build.returncode == 0, build.stdout + build.stderr
    snapshot = json.loads(base64.b64decode(rendered["snapshot"]))
    aliases = snapshot["profiles"]["balanced"]["candidate_models"]
    def scoring(scores=None, choice=None):
        scores = scores or {a: (0.5 if a in aliases[:2] else 0.0) for a in aliases}
        return {"answers": {"route": {"type": "choice", "choice": choice or aliases[0], "probabilities": scores}}}
    fixtures = {p: {"profile": p, "scoring": scoring()} for p in ("balanced", "cost", "quality")}
    fixtures["omitted"] = {"scoring": scoring()}
    fixtures.update({f"status-{s}": {"status": s, "scoring": scoring()} for s in (301, 400, 401, 403, 404, 415, 422, 429, 500, 503)})
    for name, value in {"boolean": True, "string": "0.5", "negative": -1, "infinity": float("inf"), "nan": float("nan"), "too-large": 2}.items():
        scores = {a: (value if a == aliases[0] else 0.0) for a in aliases}
        fixtures[name] = {"scoring": scoring(scores)}
    fixtures["extra-alias"] = {"scoring": scoring({**{a: 0.0 for a in aliases}, "evil": 1})}
    fixtures["bad-choice"] = {"scoring": scoring(choice="evil")}
    fixtures["inconsistent-choice"] = {"scoring": scoring(choice=aliases[-1])}
    fixtures["sum"] = {"scoring": scoring({a: 0.0 for a in aliases})}
    fixtures["oversize"] = {"raw": "x" * 65537, "scoring": scoring()}
    fixtures["bad-json"] = {"raw": "{", "scoring": scoring()}
    fixtures["maximum"] = {"maximum": 1025, "scoring": scoring()}
    fixtures["elapsed"] = {"elapsed": 120001, "scoring": scoring()}
    fixtures["redacted-bound"] = {"messages": [{"role": "user", "content": "x" * 4801}], "scoring": scoring()}
    import copy
    import hashlib
    for count in (0, 1, 2):
        dynamic = copy.deepcopy(snapshot)
        for alias in aliases[count:]:
            dynamic["candidates"][alias]["price"] = None
        pool = aliases if count < 2 else aliases[:count]
        fixtures[f"cost-known-{count}"] = {"profile": "cost", "snapshot": dynamic,
            "scoring": scoring({a: (1 if a == pool[0] else 0) for a in pool}, pool[0])}
        if count >= 2:
            fixtures["cost-outside-dynamic-pool"] = {"profile": "cost", "snapshot": dynamic, "scoring": scoring()}
        projection = {"schema": 1, "pool_version": snapshot["version"], "rate_card_version": 9,
            "revision": "live-rate-card-v9", "source": "rate-card", "prices": {
                alias: {"input": "0", "output": "1", "status": "configured", "revision": "row-v9",
                    "source_url": "", "source_model": "", "currency": "USD", "unit": "per_million_tokens"}
                if alias in aliases[:count] else None for alias in aliases}}
        compact = lambda p: json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        projection["sha256"] = hashlib.sha256(compact(projection).encode()).hexdigest()
        fixtures[f"cost-applied-{count}"] = {"profile": "cost", "pricing": compact(projection),
            "scoring": scoring({a: (1 if a == pool[0] else 0) for a in pool}, pool[0])}
    execution = subprocess.run([dotnet, str(folder / "bin/Debug" / f"net{major}.0/Harness.dll")],
        input=json.dumps({"fixtures": fixtures, "snapshot": json.dumps(snapshot)}), capture_output=True,
        text=True, env=env, timeout=60)
    assert execution.returncode == 0, execution.stderr
    return json.loads(execution.stdout)


@pytest.mark.parametrize("profile", ["balanced", "cost", "quality", "omitted"])
def test_real_rendered_csharp_wire_result_and_metadata(expressions, profile):
    result = expressions[profile]
    assert not result["rejected"]
    assert result["routing"]["routing_profile"] == ("balanced" if profile == "omitted" else profile)
    assert result["routing"]["selected_model"] == "DeepSeek-V4-Flash"  # stable ordinal tie, not quality ranking
    assert result["routing"]["fallback_used"] is False
    assert result["routing"]["decision_overhead"]["cost_usd"] is None
    assert result["wire"]["state"]["messages"][0]["content"] == "REDACTED"
    assert set(result["wire"]) == {"model", "state", "questions"}
    assert result["completion"]["model"] == "provider-actual-model"
    assert result["completion"]["usage"] == {"total_tokens": 7}


@pytest.mark.parametrize("name", [*[f"status-{s}" for s in (301, 400, 401, 403, 404, 415, 422, 429, 500, 503)],
    "boolean", "string", "negative", "infinity", "nan", "too-large", "extra-alias", "bad-choice",
    "inconsistent-choice", "sum", "oversize", "bad-json", "maximum", "elapsed"])
def test_real_rendered_csharp_scoring_errors_fail_closed(expressions, name):
    assert expressions[name]["rejected"] is True


def test_real_rendered_csharp_redaction_bound_before_scoring(expressions):
    assert expressions["redacted-bound"]["wire_rejected"] is True


@pytest.mark.parametrize("count", [0, 1, 2])
def test_actual_wire_and_response_share_dynamic_cost_pool_without_price_gate(expressions, count):
    result = expressions[f"cost-known-{count}"]
    assert result["rejected"] is False
    assert result["routing"]["cost_suitability_fallback"] is (count < 2)
    assert len(result["wire"]["questions"]["route"]["criteria"]) == (6 if count < 2 else 2)
    assert result["routing"]["config_version"] == expressions["balanced"]["routing"]["config_version"]
    assert result["routing"]["decision_overhead"]["cost_usd"] is None


def test_actual_response_rejects_alias_outside_dynamic_criteria(expressions):
    assert expressions["cost-outside-dynamic-pool"]["rejected"] is True


@pytest.mark.parametrize("count", [0, 1, 2])
def test_applied_pricing_flows_through_native_wire_result_and_informational_trace(expressions, count):
    result = expressions[f"cost-applied-{count}"]
    assert result["rejected"] is False
    assert result["routing"]["pricing_revision"] == "live-rate-card-v9"
    assert result["routing"]["pricing_source"] == "rate-card"
    assert result["routing"]["pricing_stale"] is None
    for name in ("pricing_revision", "pricing_sha256", "pricing_source", "cost_suitability_fallback"):
        assert result["trace"][name] == result["routing"][name]
    assert result["trace"]["cost_usd"] is None
    criteria = result["wire"]["questions"]["route"]["criteria"]
    assert len(criteria) == (6 if count < 2 else 2)
    descriptors = [json.loads(row) for row in criteria.values()]
    assert all(d["price"] is None or d["price"]["input"] == "0" for d in descriptors)
    assert all(d["price_status"] == ("unknown" if d["price"] is None else "configured") for d in descriptors)