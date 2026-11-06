"""Bounded source-only mock/native check. Supply a NEW empty evidence destination.

No init, restore, cloud, state, credentials, historical controllers or inference.
Synthetic provider limits are fixtures, NEVER a production release contract.
"""
import ast
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
TF = Path("C:/Program Files/Terraform/terraform.exe")
DOTNET = Path("C:/Program Files/dotnet/dotnet.exe")
SDK = DOTNET.parent / "sdk/10.0.303"


def compile_expressions(home, expressions, run):
    """Compile selected actual rendered expressions; no APIM/service emulation."""
    harness = home / "csharp"
    harness.mkdir()
    source = r'''
using System;
using System.Linq;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
public class Body {
    public string Json;
    public T As<T>(bool preserveContent) {
        return typeof(T) == typeof(string) ? (T)(object)Json : JsonConvert.DeserializeObject<T>(Json);
    }
}
public class Message { public Body Body; }
public class Context {
    public Message Request;
    public Message Response;
    public Dictionary<string, object> Variables = new Dictionary<string, object>();
}
public class Expressions {
    Context context = new Context();
    public JToken Execute(JObject fixture) {
        var request = (JObject)fixture["_request"];
        context.Variables["aiflux-model"] = (string)fixture["_alias"] ?? (string)request["model"] ?? "claude-sonnet-5-5";
        context.Variables["aiflux-backend-attempt"] = 1;
        context.Variables["aiflux-request-json"] = request.ToString();
        context.Request = new Message { Body = new Body { Json = request.ToString() } };
        context.Response = new Message { Body = new Body { Json = fixture.ToString() } };
        switch ((string)fixture["_kind"] ?? "normalize") {
            DISPATCH
            default: throw new Exception("Unknown fixture kind");
        }
    }
    METHODS
}
public class Program {
    public static void Main() {
        // Redirected Windows console defaults can otherwise replace Unicode
        // before Python reads the actual expression result as UTF-8.
        Console.InputEncoding = new System.Text.UTF8Encoding(false);
        Console.OutputEncoding = new System.Text.UTF8Encoding(false);
        var results = new JObject();
        foreach (var item in JObject.Parse(Console.In.ReadToEnd()).Properties()) {
            try { results[item.Name] = new Expressions().Execute((JObject)item.Value); }
            catch (Exception) { results[item.Name] = new JObject { ["rejected"] = true }; }
        }
        Console.WriteLine(results.ToString(Formatting.None));
    }
}
'''
    methods, dispatch = [], []
    for index, (name, expression) in enumerate(expressions.items()):
        if not expression.startswith("@{") or not expression.endswith("}"):
            raise AssertionError("Expected actual multiline policy expression: " + name)
        (home / f"expression-{index}.txt").write_text(expression, encoding="utf-8")
        method = f"Expression{index}"
        boolean = name == "shape"
        methods.append(("bool " if boolean else "string ") + method + "() " + expression[1:])
        returned = ('new JObject { ["rejected"] = ' + method + '() }') if boolean else f"JToken.Parse({method}())"
        dispatch.append(f'case {json.dumps(name)}: return {returned};')
    source = source.replace("DISPATCH", "\n".join(dispatch)).replace("METHODS", "\n".join(methods))
    (harness / "Harness.cs").write_text(source, encoding="utf-8")
    refs = sorted((DOTNET.parent / "packs/Microsoft.NETCore.App.Ref/10.0.11/ref/net10.0").glob("*.dll"))
    if not refs or not (SDK / "Newtonsoft.Json.dll").is_file():
        raise RuntimeError("Installed native prerequisites missing; no install allowed")
    shutil.copyfile(SDK / "Newtonsoft.Json.dll", harness / "Newtonsoft.Json.dll")
    (harness / "Harness.runtimeconfig.json").write_text(json.dumps({"runtimeOptions": {
        "tfm": "net10.0", "framework": {"name": "Microsoft.NETCore.App", "version": "10.0.11"}}}))
    arguments = ["-nologo", "-target:exe", f'-out:"{harness / "Harness.dll"}"']
    arguments += [f'-r:"{p}"' for p in refs + [harness / "Newtonsoft.Json.dll"]]
    arguments += [f'"{harness / "Harness.cs"}"']
    (harness / "compiler.rsp").write_text("\n".join(arguments), encoding="utf-8")
    compiled = run("csharp-compile", [DOTNET, SDK / "Roslyn/bincore/csc.dll", "@" + str(harness / "compiler.rsp")])
    if compiled.returncode:
        raise RuntimeError("Native expression compilation failed; inspect retained output")
    return harness


def main(destination):
    home = Path(destination).resolve()
    home.mkdir(parents=True, exist_ok=False)
    checks = []
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith(("TF_CLI_ARGS", "TF_VAR_", "ARM_", "AZURE_")) and k != "TF_DATA_DIR"}
    environment.update(CHECKPOINT_DISABLE="1", TF_IN_AUTOMATION="1",
                       TF_CLI_CONFIG_FILE=str(ROOT / ".deployment/terraform.rc"),
                       DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")

    def run(label, command, **kwargs):
        result = subprocess.run([str(x) for x in command], capture_output=True,
                                text=True, encoding="utf-8", timeout=180, env=environment, **kwargs)
        (home / f"{label}.stdout.txt").write_text(result.stdout, encoding="utf-8")
        (home / f"{label}.stderr.txt").write_text(result.stderr, encoding="utf-8")
        checks.append({"label": label, "exit_code": result.returncode})
        return result

    def check(value, description):
        if not value:
            raise AssertionError(description)
        checks.append({"assertion": description, "passed": True})

    try:
        route = home / "render/infra/project-route"
        route.mkdir(parents=True)
        source = ROOT / "infra/project-route"
        for path in source.glob("*.tf"):
            if path.name == "model-access.tf":
                continue  # Paused Feature2 is NOT validated or executed by this harness.
            shutil.copyfile(path, route / path.name)
        # Test-only identity adapter for the paused Feature2 hook. Its external
        # provider is not installed; do not install/init it or exercise its code.
        staged_main = (route / "main.tf").read_text()
        external = '    external = {\n      source  = "hashicorp/external"\n      version = "= 2.3.5"\n    }\n'
        reference = '!var.model_access_enabled || try(data.external.model_access_receipt[0].result.valid == "true", false)'
        check(staged_main.count(external) == 1 and staged_main.count(reference) == 1,
              "bounded paused-hook identity adapter anchors")
        (route / "main.tf").write_text(staged_main.replace(external, "").replace(reference, "!var.model_access_enabled"))
        (route / "offline-paused-identity.tf").write_text('''
variable "model_access_enabled" {
    type = bool
    default = false
    validation {
        condition = !var.model_access_enabled
        error_message = "Paused feature cannot activate in this isolated cap harness."
    }
}
locals { model_access_policy = local.foundry_eight_policy }
''')
        shutil.copyfile(source / ".terraform.lock.hcl", route / ".terraform.lock.hcl")
        # Provider cache ONLY. No state, plans, credentials, user tfvars or backend metadata.
        shutil.copytree(source / ".terraform/providers", route / ".terraform/providers")
        for folder in ("gateway/catalog", "gateway/policies", "services/control-plane/src/aiflux/pricing"):
            shutil.copytree(ROOT / folder, home / "render" / folder)
        manifest = json.loads((ROOT / "gateway/catalog/foundry-successor22-candidate-routes.json").read_text())
        aliases = sorted(set(manifest["routes"]) | {"glm-5.3"})
        contract = {"schema": 1, "allowance": 4096, "provider_limits": {a: 8192 for a in aliases}}
        testdir = route / "tests"
        testdir.mkdir()
        raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        (testdir / "synthetic.json").write_bytes(raw)
        # Existing production resource enablement stays false. Render Auto composition
        # as an OUTPUT, never spoof runtime evidence or invoke paused Feature2 tests.
        (route / "offline-outputs.tf").write_text('''
output "offline_auto" { value = local.auto_with_error }
output "offline_version" { value = local.auto_completion_version }
''')
        (testdir / "completion.tftest.hcl").write_text('''
mock_provider "azapi" {}
mock_provider "azurerm" {}
variables {
  enabled = false
  poc_settings_bootstrap_enabled = false
  route_manifest_path = "../../gateway/catalog/foundry-successor22-candidate-routes.json"
  completion_token_limit = 4096
  completion_limits_path = "tests/synthetic.json"
    glm_enabled = true
    persistent_poc_authorized = true
    demo_authorized = true
    rpm_limit = 60
    tpm_limit = 300000
    daily_token_quota = 20000000
    daily_call_allowance = 50000
}
run "synthetic_4096" {
  command = plan
  assert {
    condition = length(local.all_aliases) == 22 && alltrue([for limit in values(local.effective_completion_limits) : limit == 4096]) && length(local.auto_candidates) == 6 && length(local.auto_profiles) == 3
    error_message = "Exact all22/6/3 ceilings required."
  }
  assert {
    condition = !var.auto_routing_enabled && !var.poc_controls_enabled && !var.admin_settings_enabled && length(azapi_resource.project_policy) == 0
    error_message = "Fixture cannot activate resources or runtime features."
  }
}
run "no_optin_4096_rejected" {
  command = plan
  variables { completion_limits_path = "" }
  expect_failures = [var.completion_limits_path]
}
''', encoding="utf-8")
        validation = run("validate", [TF, "validate", "-json"], cwd=route)
        check(validation.returncode == 0, "isolated cap harness Terraform validate (NOT complete dirty module)")
        rendered = run("mock", [TF, "test", "-json", "-verbose",
                                "-filter=tests\\completion.tftest.hcl"], cwd=route)
        check(rendered.returncode == 0, "isolated mocked Terraform tests")
        events = [json.loads(line) for line in rendered.stdout.splitlines() if line.strip()]
        summary = next(e["test_summary"] for e in events if e.get("type") == "test_summary")
        check(summary["passed"] == 2 and summary["failed"] == 0
              and summary.get("errored", 0) == 0 and summary.get("skipped", 0) == 0,
              "both mock runs actually executed with no errors/skips")
        plan = next(e["test_plan"] for e in events if e.get("type") == "test_plan"
                    and e.get("@testrun") == "synthetic_4096")
        outputs = plan["output_changes"]
        policy = outputs["candidate_policy"]["after"]
        auto = outputs["offline_auto"]["after"]
        (home / "explicit-policy.xml").write_text(policy, encoding="utf-8")
        (home / "auto-policy.xml").write_text(auto, encoding="utf-8")
        original = hashlib.sha256((ROOT / "services/control-plane/src/aiflux/pricing/auto-routing-defaults.json").read_bytes()).hexdigest()
        expected = hashlib.sha256(f"{original}:{hashlib.sha256(raw).hexdigest()}".encode()).hexdigest()
        check(outputs["offline_version"]["after"] == expected, "Terraform/Python successor version parity")

        # Reuse ONLY the pure local XML parser body; no historical module import,
        # global controller, fixture runner, intent or evidence-directory replay.
        old = ast.parse((ROOT / "tests/contract/test_foundry_eight_gateway.py").read_text())
        helpers = ast.Module(body=[n for n in old.body if isinstance(n, ast.FunctionDef)
            and n.name == "parse_policy"], type_ignores=[])
        namespace = {"HOME": home, "DOTNET": DOTNET, "SDK": SDK, "run": run,
                     "json": json, "shutil": shutil, "re": re, "ET": ET}
        exec(compile(helpers, "pure-native-helpers", "exec"), namespace)
        # Auto shape + final native transforms from actual explicit render. Auto is
        # composed BEFORE final native wrapping, exactly as the production module.
        parse = namespace["parse_policy"]
        explicit_node = parse(policy)
        auto_node = parse(auto)
        shape = next(n.attrib["condition"] for n in auto_node.findall("./inbound//when")
                     if "body.Properties().Any" in n.attrib.get("condition", ""))
        node = next(n for n in explicit_node.findall("./inbound//when")
                    if "body.Properties().Any" in n.attrib.get("condition", ""))
        node.attrib["condition"] = shape
        expressions = {"shape": shape,
            "normalize": explicit_node.find(".//set-body[@id='aiflux-anthropic-normalization']").text,
            "usage": explicit_node.find(".//set-variable[@name='aiflux-finops-usage']").attrib["value"]}
        translations = {}
        for alias in aliases:
            condition = '@((string)context.Variables["aiflux-model"] == "' + alias + '")'
            branches = [n for n in explicit_node.findall("./inbound//when") if n.attrib.get("condition") == condition]
            bodies = [b.text for n in branches for b in n.findall("set-body") if (b.text or "").startswith("@{")]
            if bodies:
                check(len(bodies) == 1, "one conversion for " + alias)
                expressions["convert:" + alias] = bodies[0]
                translations[alias] = manifest["routes"][alias]["token_parameter"]
        harness = compile_expressions(home, expressions, run)
        fixtures = {}
        expected_rejection = {}
        def shape_case(name, request, rejected):
            fixtures[name] = {"_kind": "shape", "_request": request}
            expected_rejection[name] = rejected
        for alias in aliases + ["auto"]:
            base = {"model": alias, "messages": [{"role": "user", "content": "fixture"}], "stream": False}
            for maximum in (1, 1024, 1025, 4096, 4097, 0, -1, 1.5, True, "4096", None):
                shape_case(f"shape:{alias}:{maximum!r}", base | {"max_completion_tokens": maximum},
                           type(maximum) is not int or not 1 <= maximum <= 4096)
            shape_case(f"missing:{alias}", base, True)
            shape_case(f"stream:{alias}", base | {"stream": True, "max_completion_tokens": 4096}, True)
        for profile in ("balanced", "cost", "quality"):
            shape_case("profile:" + profile, {"model": "auto", "routing_profile": profile,
                "messages": [{"role": "user", "content": "fixture"}], "max_completion_tokens": 4096}, False)
        long_text = "start:" + ("A\U0001f600\u6f22" * 5000) + ":LATE_SENTINEL"
        base = {"id": "synthetic-only", "content": [{"type": "text", "text": long_text}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 4096},
                "_request": {"max_completion_tokens": 4096}}
        fixtures["long-unicode"] = base
        fixtures["over-output"] = deepcopy(base)
        fixtures["over-output"]["usage"]["output_tokens"] = 4097
        fixtures["long-unicode-usage"] = deepcopy(base) | {"_kind": "usage"}
        for maximum in (1, 1024, 1025, 4096):
            for alias in translations:
                fixtures[f"convert:{alias}:{maximum}"] = {"_kind": "convert:" + alias, "_alias": alias,
                    "_request": {"model": alias, "messages": [{"role": "user", "content": "fixture"}],
                                 "max_completion_tokens": maximum, "stream": False}}
        (home / "fixtures.json").write_text(json.dumps(fixtures), encoding="utf-8")
        native = run("native", [DOTNET, harness / "Harness.dll"], input=json.dumps(fixtures))
        check(native.returncode == 0, "native expression execution")
        results = json.loads(native.stdout)
        for name, rejected in expected_rejection.items():
            check(results[name].get("rejected") is rejected, name)
        check(results["long-unicode"]["choices"][0]["message"]["content"] == long_text,
              "native normalization preserves complete late Unicode suffix >1024 tokens (not safety service proof)")
        check(results["over-output"].get("rejected") is True, "native output usage above allowance rejected")
        check(results["long-unicode-usage"]["output_tokens"] == 4096,
              "native usage accounting retains measured 4096 output tokens")
        for name, result in results.items():
            if name.startswith("convert:"):
                maximum = int(name.rsplit(":", 1)[1])
                parameter = translations[name.split(":")[1]]
                other = "max_tokens" if parameter == "max_completion_tokens" else "max_completion_tokens"
                check(result[parameter] == maximum and other not in result,
                      name + ": exact native allowance, no clamp")
        check(explicit_node.find("./backend/forward-request").attrib["buffer-response"] == "true",
              "final response stays buffered")
        outbound = list(explicit_node.find("outbound").iter())
        safety = explicit_node.find("./outbound//llm-content-safety")
        normalize = explicit_node.find(".//set-body[@id='aiflux-anthropic-normalization']")
        final = explicit_node.find(".//set-variable[@name='aiflux-native-answer']")
        check(safety is not None and safety.attrib["window-size"] == "1000"
              and safety.attrib["window-overlap-size"] == "100", "unchanged output window configuration")
        check(outbound.index(normalize) < outbound.index(safety) < outbound.index(final),
              "complete normalized response crosses safety before final native return")
        # Configuration-level window coverage oracle, NOT the opaque Azure safety
        # implementation/tokenizer/classifier. No claim that this tests live scanning.
        tokens = ["safe"] * 4096 + ["LATE_SENTINEL"]
        windows = [tokens[i:i + 1000] for i in range(0, len(tokens), 900)]
        check(any("LATE_SENTINEL" in w for w in windows), "synthetic late-window coverage oracle")
        check(len(explicit_node.findall(".//retry")) == 0
              and len(explicit_node.findall(".//llm-content-safety")) == 3,
              "no retries and all three safety nodes retained")
        checks.append({"native_fixture_count": len(fixtures), "live_safety_tested": False,
                       "provider_compatibility_proved": False, "cloud_operations": 0})
    finally:
        (home / "result.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps({"status": "passed", "checks": len(checks), "evidence": str(home)}))


if __name__ == "__main__":
    main(sys.argv[1])