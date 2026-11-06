"""Standalone offline gateway suite; no pytest conftest, restores, init or cloud.

Run this file with the configured Python. Results are exclusively created under
.deployment/foundry-eight-gateway-offline-<UTC>/. Terraform uses only mock
providers and a copied, state-free root; only foundry-eight.tftest.hcl runs.
C# is compiled directly with the installed SDK/compiler/reference assemblies
and SDK Newtonsoft DLL, not NuGet, dotnet build, roll-forward or tool installs.
"""

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[2]
TF = Path("C:/Program Files/Terraform/terraform.exe")
DOTNET = Path("C:/Program Files/dotnet/dotnet.exe")
SDK = DOTNET.parent / "sdk/10.0.303"
OWNED = ["infra/project-route/main.tf", "infra/project-route/foundry-eight.tf",
         "infra/project-route/tests/foundry-eight.tftest.hcl",
         "gateway/policies/dev-openai.xml.tftpl", str(Path(__file__).relative_to(ROOT)).replace("\\", "/")]
HOME = ROOT / ".deployment" / ("foundry-eight-gateway-offline-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
ENV = os.environ | {"CHECKPOINT_DISABLE": "1", "TF_IN_AUTOMATION": "1",
                    "TF_CLI_CONFIG_FILE": str(ROOT / ".deployment/terraform.rc"),
                    "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"}
# Never inherit arguments capable of changing the selected test/remote behavior.
ENV = {key: value for key, value in ENV.items() if not key.startswith("TF_CLI_ARGS") and key != "TF_DATA_DIR"}
COMMANDS = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    path = HOME / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def protected():
    paths = list((ROOT / "gateway/catalog").glob("*.json"))
    paths += list((ROOT / "gateway/policies").glob("auto*"))
    paths += [ROOT / "infra/project-route" / name for name in
              ("auto-routing.tf", "auto-staging.tf", "external.tf", "fireworks.tf", "poc-controls.tf")]
    paths += [ROOT / "services/control-plane/src/aiflux" / name for name in ("auto_snapshot.py", "decision_router.py")]
    paths += list((ROOT / "services/control-plane/src/aiflux/pricing").glob("auto*"))
    paths += [ROOT / "services/control-plane/src/aiflux/pricing/rates-20261027.json"]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in paths if p.is_file()}


def run(name, args, cwd=None, stdin=None):
    result = subprocess.run([str(x) for x in args], cwd=cwd or ROOT, env=ENV,
                            input=stdin, encoding="utf-8", capture_output=True, timeout=240)
    (HOME / (name + ".stdout.txt")).write_text(result.stdout, encoding="utf-8")
    (HOME / (name + ".stderr.txt")).write_text(result.stderr, encoding="utf-8")
    COMMANDS.append({"name": name, "argv": [str(x) for x in args], "cwd": str(cwd or ROOT), "exit_code": result.returncode})
    return result


def structural(element):
    """XML formatting only is irrelevant; all expression/body characters stay."""
    text = element.text or ""
    if not text.strip():
        text = ""
    return [element.tag, dict(sorted(element.attrib.items())), text, [structural(child) for child in element]]


def parse_policy(raw):
    # ARM's XML export encodes expression attribute newlines as character refs.
    # A normal XML parser otherwise replaces literal attribute LF with spaces
    # (including C# // comment terminators!). Preserve exact expression bytes,
    # not token/whitespace folding, and never rewrite CDATA bodies or comments.
    parts = re.split(r'(<!\[CDATA\[.*?\]\]>|<!--.*?-->)', raw, flags=re.S)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r'''(\s[\w:-]+=)("[^"]*"|'[^']*')''',
                          lambda m: m[1] + m[2].replace("\n", "&#xA;").replace("\t", "&#x9;"), parts[i])
    return ET.fromstring("".join(parts))


def prepare_render():
    stage = HOME / "render"
    route = stage / "infra/project-route"
    route.mkdir(parents=True)
    for path in (ROOT / "infra/project-route").glob("*.tf"):
        shutil.copyfile(path, route / path.name)
    shutil.copyfile(ROOT / "infra/project-route/.terraform.lock.hcl", route / ".terraform.lock.hcl")
    # Provider artifacts only: NEVER copy state, lock info, auto.tfvars or plans.
    shutil.copytree(ROOT / "infra/project-route/.terraform", route / ".terraform")
    for folder in ("gateway/catalog", "gateway/policies", "services/control-plane/src/aiflux/pricing"):
        shutil.copytree(ROOT / folder, stage / folder)
    (route / "tests").mkdir()
    shutil.copyfile(ROOT / "infra/project-route/tests/foundry-eight.tftest.hcl", route / "tests/foundry-eight.tftest.hcl")
    # Check only the three owned files without writing. Terraform fmt on stdin
    # adds a terminal newline even when fmt -check accepts that file unchanged.
    # Use the actual formatter check, not a byte comparison to its stdin output.
    formats = {}
    for relative in OWNED[:3]:
        result = run("fmt-" + Path(relative).name, [TF, "fmt", "-check", "-no-color", ROOT / relative])
        formats[relative] = {"exit_code": result.returncode, "formatted": result.returncode == 0}
    save("fmt.json", formats)
    validation = run("terraform-validate", [TF, "validate", "-json"], cwd=route)
    save("validate.json", json.loads(validation.stdout))
    result = run("terraform-mocked", [TF, "test", "-no-color", "-json", "-verbose", "-filter=tests\\foundry-eight.tftest.hcl"], cwd=route)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    summary = [event for event in events if event.get("type") == "test_summary"]
    save("terraform-summary.json", summary)
    renders = {}
    for event in events:
        if event.get("type") != "test_plan":
            continue
        plan = event["test_plan"]
        value = plan.get("output_changes", {}).get("candidate_policy", {}).get("after")
        if value:
            name = event.get("@testrun", "unknown")
            renders[name] = value
            (HOME / ("rendered-" + name + ".xml")).write_text(value, encoding="utf-8")
    return formats, validation, result, summary, renders


def compile_csharp(policy):
    node = parse_policy(policy)
    normalize = node.find(".//set-body[@id='aiflux-anthropic-normalization']").text
    usage = node.find(".//set-variable[@name='aiflux-finops-usage']").attrib["value"]
    branch = next(n for n in node.findall("./inbound//when") if n.attrib.get("condition") == '@((string)context.Variables["aiflux-model"] == "claude-opus-5-5-fast")')
    conversion = branch.find("set-body").text
    standard_branch = next(n for n in node.findall("./inbound//when") if n.attrib.get("condition") == '@((string)context.Variables["aiflux-model"] == "claude-sonnet-5-5")')
    standard_conversion = standard_branch.find("set-body").text
    shape = next(n.attrib["condition"] for n in node.findall("./inbound//when") if 'body.Properties().Any' in n.attrib.get("condition", ""))
    for name, expression in {"normalize": normalize, "usage": usage, "conversion": conversion, "shape": shape}.items():
        (HOME / (name + ".cs-expression.txt")).write_text(expression, encoding="utf-8")
    harness = HOME / "csharp"
    harness.mkdir()
    source = r'''
using System;
using System.Linq;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
public class Body {
    public string Json;
    public T As<T>(bool preserveContent) { return JsonConvert.DeserializeObject<T>(Json); }
}
public class Message { public Body Body; }
public class Context {
    public Message Request;
    public Message Response;
    public Dictionary<string, object> Variables = new Dictionary<string, object>();
}
public class Expressions {
    Context context = new Context();
    public JObject Execute(JObject fixture) {
        var request = fixture["_request"] as JObject ?? JObject.Parse("{\"model\":\"claude-sonnet-5-5\",\"messages\":[{\"role\":\"user\",\"content\":\"REDACTED\"}],\"max_completion_tokens\":1024,\"stream\":false}");
        context.Variables["aiflux-model"] = (string)fixture["_alias"] ?? "claude-sonnet-5-5";
        context.Variables["aiflux-backend-attempt"] = 1;
        context.Variables["aiflux-request-json"] = request.ToString();
        context.Request = new Message { Body = new Body { Json = request.ToString() } };
        context.Response = new Message { Body = new Body { Json = fixture.ToString() } };
        var kind = (string)fixture["_kind"] ?? "normalize";
        if (kind == "shape") { return new JObject { ["rejected"] = Validate() }; }
        return JObject.Parse(kind == "usage" ? Usage() : kind == "convert" ? ((string)context.Variables["aiflux-model"] == "claude-opus-5-5-fast" ? Convert() : StandardConvert()) : Normalize());
    }
    string Normalize() NORMALIZE
    string Usage() USAGE
    string Convert() CONVERT
    string StandardConvert() STANDARD_CONVERT
    bool Validate() SHAPE
}
public class Program {
    public static void Main() {
        var results = new JObject();
        foreach (var item in JObject.Parse(Console.In.ReadToEnd()).Properties()) {
            try { results[item.Name] = new Expressions().Execute((JObject)item.Value); }
            catch (Exception) { results[item.Name] = new JObject { ["rejected"] = true }; }
        }
        Console.WriteLine(results.ToString(Formatting.None));
    }
}
'''
    for label, expr in (("NORMALIZE", normalize), ("USAGE", usage), ("STANDARD_CONVERT", standard_conversion), ("CONVERT", conversion), ("SHAPE", shape)):
        assert expr.startswith("@{") and expr.endswith("}")
        source = source.replace(label, expr[1:])
    (harness / "Harness.cs").write_text(source, encoding="utf-8")
    refs = sorted((DOTNET.parent / "packs/Microsoft.NETCore.App.Ref/10.0.11/ref/net10.0").glob("*.dll"))
    if not refs or not (SDK / "Newtonsoft.Json.dll").is_file():
        raise RuntimeError("Installed .NET10 reference assemblies or SDK Newtonsoft.Json unavailable; no install/restore allowed")
    shutil.copyfile(SDK / "Newtonsoft.Json.dll", harness / "Newtonsoft.Json.dll")
    (harness / "Harness.runtimeconfig.json").write_text(json.dumps({"runtimeOptions": {"tfm": "net10.0", "framework": {"name": "Microsoft.NETCore.App", "version": "10.0.11"}}}), encoding="utf-8")
    arguments = ["-nologo", "-target:exe", '-out:"' + str(harness / "Harness.dll") + '"']
    arguments += ['-r:"' + str(path) + '"' for path in refs + [harness / "Newtonsoft.Json.dll"]]
    arguments += ['"' + str(harness / "Harness.cs") + '"']
    (harness / "compiler.rsp").write_text("\n".join(arguments), encoding="utf-8")
    compiled = run("csharp-compile", [DOTNET, SDK / "Roslyn/bincore/csc.dll", "@" + str(harness / "compiler.rsp")])
    if compiled.returncode:
        raise RuntimeError("C# compile failed: " + compiled.stdout + compiled.stderr)
    return harness


class GatewayOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formats, cls.validation, cls.mocked, cls.summary, cls.renders = prepare_render()

    def test_01_fmt(self):
        self.assertTrue(all(v["formatted"] and v["exit_code"] == 0 for v in self.formats.values()), self.formats)

    def test_02_validate(self):
        self.assertEqual(self.validation.returncode, 0, self.validation.stdout)

    def test_03_mocked_only_new_suite(self):
        self.assertEqual(self.mocked.returncode, 0, "Read terraform-mocked.stdout.txt")
        self.assertEqual(len(self.summary), 1)
        self.assertGreater(self.summary[0]["test_summary"]["passed"], 0)
        self.assertEqual(self.summary[0]["test_summary"]["failed"], 0)

    def test_04_exact_membership_and_historical_behavior(self):
        historical = self.renders["historical_twelve_remain_opted_out"]
        current = self.renders["explicit_manifest_is_exact_twenty_plus_external"]
        old_node, new_node = parse_policy(historical), parse_policy(current)
        def advertised(node):
            return next(json.loads(n.text)["data"] for n in node.findall("./inbound//set-body") if (n.text or "").startswith('{"data":'))
        old_aliases = {x["id"] for x in advertised(old_node)}
        new_aliases = {x["id"] for x in advertised(new_node)}
        manifest = json.loads((ROOT / "gateway/catalog/foundry-eight-candidate-routes.json").read_text())
        self.assertEqual(new_aliases, set(manifest["routes"]) | {"glm-5.3"})
        self.assertEqual(len(old_aliases), 13)
        self.assertEqual(len(new_aliases - old_aliases), 8)
        # Every original alias has the identical inbound backend selection body.
        for alias in old_aliases - {"glm-5.3"}:
            condition = '@((string)context.Variables["aiflux-model"] == "' + alias + '")'
            old = next(n for n in old_node.findall("./inbound//when") if n.attrib.get("condition") == condition)
            new = next(n for n in new_node.findall("./inbound//when") if n.attrib.get("condition") == condition)
            self.assertEqual(structural(old), structural(new), alias)
        # Compare baseline render with the retained active XML (credential values
        # intentionally redacted by that collector; never emit or restore them).
        retained = json.loads((ROOT / ".deployment/foundry-eight-20261030/continuation01/policy-xml.json").read_text())
        retained_node = ET.fromstring(retained["properties"]["value"])
        # Standard ARM xml export may retain one expression entity layer.
        def decode_node(n):
            import html
            for key, value in n.attrib.items():
                if value.startswith("@"):
                    n.attrib[key] = html.unescape(value)
            if n.text and n.text.startswith("@"):
                n.text = html.unescape(n.text)
            for child in n:
                decode_node(child)
        decode_node(retained_node)
        for n in (old_node, retained_node):
            for header in n.findall('.//set-header[@name="Authorization"]'):
                value = header.find("value")
                if value is not None:
                    value.text = "REDACTED_CREDENTIAL_COMPARISON_ONLY"
        # Formatting of CDATA/expressions is significant except export CRLF.
        self.assertEqual(structural(old_node), structural(retained_node), "Historical policy differs from actual retained active behavior")
        save("render-verification.json", {"old_aliases": sorted(old_aliases), "new_aliases": sorted(new_aliases), "old13_inbound_routes_equal": True, "historical_active_policy_structural_equal_redacted_credentials_only": True})

    def test_05_safety_and_clean_native_release(self):
        node = parse_policy(self.renders["explicit_manifest_is_exact_twenty_plus_external"])
        self.assertEqual(len(node.findall("./backend/forward-request")), 1)
        self.assertEqual(len(node.findall(".//retry")), 0)
        self.assertEqual(len(node.findall(".//include-fragment")), 0)
        self.assertEqual(len(node.findall(".//llm-content-safety")), 3)
        outbound = list(node.find("outbound").iter())
        norm = node.find('.//set-body[@id="aiflux-anthropic-normalization"]')
        safety = node.find("./outbound//llm-content-safety")
        final = node.find('.//set-variable[@name="aiflux-native-answer"]')
        self.assertLess(outbound.index(norm), outbound.index(safety))
        self.assertLess(outbound.index(safety), outbound.index(final))
        # Final native response is fresh, not a pass-through header blacklist.
        final_parent = next(n for n in node.findall("./outbound//when") if n.find('set-variable[@name="aiflux-native-answer"]') is not None)
        response = final_parent.find("return-response")
        allowed = {"Access-Control-Allow-Origin", "Vary", "Access-Control-Expose-Headers", "Content-Type", "Cache-Control", "x-aiflux-request-id"}
        self.assertEqual({h.attrib["name"] for h in response.findall("set-header")}, allowed)

    def test_06_actual_rendered_csharp_contracts(self):
        policy = self.renders["explicit_manifest_is_exact_twenty_plus_external"]
        harness = compile_csharp(policy)
        text = {"type": "text", "text": "Library answer."}
        base = {"id": "synthetic", "content": [text], "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 400, "cache_creation_input_tokens": 100}}
        cases = {"inclusive": base, "usage": base | {"_kind": "usage"}}
        for name in ("cache_read_input_tokens", "cache_creation_input_tokens"):
            for value in (None, "absent", -1, 0.5, True, "5", 2**31, {}, []):
                fixture = copy.deepcopy(base)
                if value == "absent":
                    del fixture["usage"][name]
                else:
                    fixture["usage"][name] = value
                cases[name + repr(value)] = fixture
        cases["docs-minimal-usage"] = base | {"usage": {"input_tokens": 100, "output_tokens": 20}}
        cases["docs-minimal-trace"] = cases["docs-minimal-usage"] | {"_kind": "usage"}
        cases["zero-caches"] = base | {"usage": base["usage"] | {"cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
        cases["overflow"] = base | {"usage": base["usage"] | {"input_tokens": 2**31 - 1}}
        cases["partial-overflow"] = base | {"usage": {"input_tokens": 2**31 - 1, "output_tokens": 20, "cache_read_input_tokens": 1}}
        invalid_usage = []
        for field in ("input_tokens", "output_tokens"):
            for value in (None, "absent", -1, 0.5, True, "5", 2**31):
                fixture = copy.deepcopy(base)
                if value == "absent":
                    del fixture["usage"][field]
                else:
                    fixture["usage"][field] = value
                name = field + repr(value)
                cases[name] = fixture
                invalid_usage.append(name)
        cases["output-cap"] = base | {"usage": base["usage"] | {"output_tokens": 1025}}
        cases["fast"] = base | {"_alias": "claude-opus-5-5-fast", "usage": base["usage"] | {"speed": "fast"}}
        cases["fast-trace"] = cases["fast"] | {"_kind": "usage"}
        for alias in ("claude-opus-5-5-fast", "claude-sonnet-5-5"):
            for speed in (None, "absent", "standard", "fast", "slow", 1):
                fixture = copy.deepcopy(base) | {"_alias": alias}
                if speed != "absent":
                    fixture["usage"]["speed"] = speed
                cases[alias + repr(speed)] = fixture
        for reason in ("end_turn", "stop_sequence", "max_tokens", "tool_use", "pause_turn", "refusal", None):
            cases["stop-" + str(reason)] = base | {"stop_reason": reason}
        thinking = {"type": "thinking", "thinking": "DO_NOT_LEAK", "signature": "DO_NOT_LEAK_SIGNATURE"}
        cases["thinking-text"] = base | {"content": [thinking, text]}
        for name, content in {"thinking-only": [thinking], "redacted": [{"type": "redacted_thinking", "data": "secret"}, text], "tool": [{"type": "tool_use"}, text], "empty": [], "blank": [text | {"text": " "}], "bad-signature": [thinking | {"signature": None}, text]}.items():
            cases[name] = base | {"content": content}
        request = {"model": "claude-opus-5-5-fast", "max_completion_tokens": 512, "stream": False,
                   "messages": [{"role": role, "content": "REDACTED-" + role} for role in ("system", "developer", "user", "assistant")]}
        cases["convert-fast"] = {"_kind": "convert", "_alias": "claude-opus-5-5-fast", "_request": request}
        standard_request = request | {"model": "claude-sonnet-5-5"}
        cases["convert-standard"] = {"_kind": "convert", "_alias": "claude-sonnet-5-5", "_request": standard_request}
        cases["shape-ok"] = {"_kind": "shape", "_request": request}
        for name, changed in {"speed": request | {"speed": "fast"}, "tools": request | {"tools": []}, "stream": request | {"stream": True}, "cap": request | {"max_completion_tokens": 1025}, "unknown": request | {"model": "mistral-medium-3-5"}, "system-only": request | {"messages": [{"role": "system", "content": "hello"}]}}.items():
            cases["shape-" + name] = {"_kind": "shape", "_request": changed}
        result = run("csharp-execution", [DOTNET, harness / "Harness.dll"], stdin=json.dumps(cases))
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(result.stdout)
        save("csharp-fixtures.json", cases)
        save("csharp-results.json", actual)
        self.assertEqual(actual["inclusive"]["usage"], {"prompt_tokens": 600, "completion_tokens": 20, "total_tokens": 620, "prompt_tokens_details": {"cached_tokens": 400, "cache_write_tokens": 100}})
        self.assertEqual(actual["usage"]["input_tokens"], 600)
        for name in ("docs-minimal-usage", "cache_read_input_tokensNone", "cache_creation_input_tokensNone", "cache_read_input_tokens'absent'", "cache_creation_input_tokens'absent'"):
            with self.subTest(case=name):
                self.assertIsNone(actual[name]["usage"]["prompt_tokens"])
                self.assertIsNone(actual[name]["usage"]["total_tokens"])
                self.assertEqual(actual[name]["usage"]["completion_tokens"], 20)
        self.assertIsNone(actual["docs-minimal-trace"]["input_tokens"])
        self.assertIsNone(actual["docs-minimal-trace"]["cached_input_tokens"])
        self.assertEqual(actual["zero-caches"]["usage"]["prompt_tokens"], 100)
        for name in cases:
            if name.startswith("cache_") and not (name.endswith("None") or name.endswith("'absent'")):
                self.assertEqual(actual[name], {"rejected": True}, name)
        for name in ["overflow", "partial-overflow", "output-cap", "thinking-only", "redacted", "tool", "empty", "blank", "bad-signature"] + invalid_usage:
            self.assertEqual(actual[name], {"rejected": True}, name)
        self.assertEqual(actual["fast"]["model"], "claude-opus-5-5-fast")
        self.assertEqual(actual["fast-trace"]["speed"], "fast")
        for alias in ("claude-opus-5-5-fast", "claude-sonnet-5-5"):
            for speed in (None, "absent", "standard", "fast", "slow", 1):
                valid = speed == "fast" if alias.endswith("-fast") else speed in ("absent", "standard")
                self.assertEqual("rejected" not in actual[alias + repr(speed)], valid, alias + repr(speed))
        for reason in ("end_turn", "stop_sequence", "max_tokens", "tool_use", "pause_turn", "refusal", None):
            self.assertEqual("rejected" not in actual["stop-" + str(reason)], reason in ("end_turn", "stop_sequence", "max_tokens"))
        self.assertEqual(actual["thinking-text"]["choices"][0]["message"]["content"], "Library answer.")
        self.assertNotIn("DO_NOT_LEAK", json.dumps(actual))
        self.assertEqual(actual["convert-fast"], {"model": "claude-opus-5-5-fast", "messages": request["messages"][2:], "system": "REDACTED-system\n\nREDACTED-developer", "max_tokens": 512, "stream": False, "speed": "fast"})
        self.assertNotIn("speed", actual["convert-standard"])
        self.assertEqual(actual["convert-standard"]["model"], "claude-sonnet-5-5")
        self.assertEqual(actual["shape-ok"], {"rejected": False})
        for name in cases:
            if name.startswith("shape-") and name != "shape-ok":
                self.assertEqual(actual[name], {"rejected": True}, name)
        save("csharp-summary.json", {"fixtures": len(cases), "all_assertions_passed": True, "runtime": "installed .NET 10.0.11", "compiler": "installed SDK 10.0.303 csc", "restore": False, "install": False})


def main():
    HOME.mkdir(parents=True, exist_ok=False)
    before = protected()
    save("intent.json", {"scope": "OFFLINE_ONLY_NEW_GATEWAY_TESTS", "started_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(), "cloud": False, "init": False, "installs": False, "auto_tests": False, "protected_before": before})
    # Python itself must never open a network connection. Subprocesses use
    # Terraform mock providers and direct offline C# compilation only.
    def deny(*args, **kwargs):
        raise AssertionError("Network forbidden in standalone offline gateway suite")
    socket.socket.connect = deny
    socket.create_connection = deny
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GatewayOffline))
    (HOME / "unittest.txt").write_text(stream.getvalue(), encoding="utf-8")
    after = protected()
    binding = {p: sha(ROOT / p) for p in OWNED}
    save("result.json", {"finished_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(), "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "skips": len(result.skipped), "passed": result.wasSuccessful() and before == after, "owned_source_sha256": binding, "protected_unchanged": before == after, "protected_after": after, "commands": COMMANDS, "cloud": False, "init": False, "installs": False, "auto_tests": False})
    print(stream.getvalue())
    print("DURABLE_OFFLINE_RESULTS=" + str(HOME))
    return 0 if result.wasSuccessful() and before == after else 1


if __name__ == "__main__":
    sys.exit(main())