"""Offline source/rendering contracts. NOT actual APIM or managed-identity proof."""
import json
import base64
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "infra" / "project-route"
POLICIES = ROOT / "gateway" / "policies"
CANDIDATES = {
    "gpt-5.4-mini", "gpt-5.6-luna", "gpt-6.1-sol", "DeepSeek-V4-Flash",
    "grok-4-1-fast-reasoning", "Kimi-K2.7-Code",
}


def terraform_binary():
    return shutil.which("terraform") or (
        "C:/Program Files/Terraform/terraform.exe"
        if Path("C:/Program Files/Terraform/terraform.exe").is_file() else None
    )


def render(extra_variables=()):
    """Evaluate locals only: console does not refresh, plan, apply or infer."""
    binary = terraform_binary()
    if not binary:
        raise unittest.SkipTest("No existing Terraform executable; no install authorized")
    expression = (
        'jsonencode({old=local.glm_policy,off=local.auto_policy,'
        'on=local.auto_with_error,final=local.policy,native_valid=local.native_manifest_valid,candidates=local.auto_candidates,'
        'model_limits=local.auto_model_limits,routes=keys(local.routes),aliases=local.all_aliases,'
        'admission=local.auto_admission,snapshot=local.auto_arguments.snapshot_base64})\n'
    )
    result = subprocess.run(
        [binary, f"-chdir={MODULE}", "console", "-no-color",
         "-var=demo_authorized=true", "-var=persistent_poc_authorized=true",
         "-var=allow_product_subscriptions=true", "-var=daily_call_allowance=1000",
         "-var=rpm_limit=60", "-var=tpm_limit=2048", "-var=completion_token_limit=1024",
         *extra_variables],
        input=expression, text=True, capture_output=True, timeout=90, cwd=ROOT,
        env={**os.environ, "CHECKPOINT_DISABLE": "1"},
    )
    if result.returncode:
        raise AssertionError(f"Offline console failed ({result.returncode}): {result.stderr}")
    return json.loads(json.loads(result.stdout.strip()))


class AutoGatewaySourceContract(unittest.TestCase):
    def test_isolated_default_off_no_new_resources_or_scope(self):
        source = (MODULE / "auto-routing.tf").read_text(encoding="utf-8")
        self.assertNotRegex(source, r'(?m)^\s*(resource|data|provider)\s+"')
        self.assertIn('variable "auto_routing_enabled" {\n  type        = bool\n  default     = false', source)
        for gate in ("!var.admin_settings_enabled", "!var.poc_controls_enabled",
                     "!var.candidate_validation", "!var.acceptance_verified",
                     "var.persistent_poc_authorized", "var.allow_product_subscriptions"):
            self.assertIn(gate, source)
        self.assertIn('var.auto_routing_runtime_evidence_sha256', source)
        self.assertNotIn('auto_routing_api_audience', source)
        self.assertIn('var.auto_routing_enabled ? local.auto_with_error : local.glm_policy', source)
        # No shared-template edits, new parameters or legacy consumers required.
        self.assertNotIn("aiflux-auto", (POLICIES / "dev-openai.xml.tftpl").read_text())

    def test_resolver_has_exact_mi_auth_and_only_trusted_redacted_payload(self):
        source = (POLICIES / "auto-resolve.xml.tftpl").read_text()
        tree = ET.fromstring("<root>" + source + "</root>")
        auth = tree.find(".//authentication-managed-identity")
        self.assertEqual(auth.get("resource"), "https://cognitiveservices.azure.com")
        self.assertEqual(auth.get("client-id"), "${gateway_client}")
        self.assertNotIn("/.default", source)
        self.assertNotIn("azurewebsites.net", source)
        request = tree.find(".//send-request")
        self.assertEqual(request.get("mode"), "new")
        self.assertEqual(request.get("ignore-error"), "true")
        self.assertEqual(request.findtext("set-url"), "https://poc-ids-token-ex-foundry.services.ai.azure.com/providers/microsoft/v1/systemone")
        payload = request.findtext("set-body")
        self.assertIn('JObject.Parse((string)context.Variables["aiflux-auto-redacted"])', payload)
        self.assertNotIn("subscription_id", payload)
        self.assertEqual(set(re.findall(r'\["([a-z_]+)"\] =(?!=)', payload)),
                 {"model", "state", "messages", "max_completion_tokens", "questions", "route", "type", "instructions", "criteria"})
        self.assertNotIn("Headers", payload)
        for name in ("x-aiflux-subscription-id", "x-aiflux-routing-profile", "x-aiflux-selected-model",
                     "x-aiflux-original-body", "x-aiflux-pii-response"):
            self.assertIsNotNone(tree.find(f'.//set-header[@name="{name}"][@exists-action="delete"]'))

    def test_fail_closed_alias_limits_and_bounded_metadata(self):
        source = (POLICIES / "auto-resolve.xml.tftpl").read_text()
        for guard in ("response.StatusCode != 200", "raw) > 65536", "${candidate_conditions}",
                      "${manifest_conditions}", "maximum > modelMaximum", "catch { return", "auto_routing_unavailable",
                      'request.Remove("routing_profile")', 'request["model"] = (string)context.Variables["aiflux-model"]',
                      "JTokenType.Float", "120000", "2147483647", "${provider_rules}"):
            self.assertIn(guard, source)
        self.assertNotIn("set-backend-service", source)
        self.assertNotIn("retry", source)
        metadata = (POLICIES / "auto-metadata.xml").read_text()
        self.assertIn('response["routing"]', metadata)
        self.assertNotIn('response["model"] =', metadata)
        self.assertNotIn('response["usage"]', metadata)
        self.assertIn('["decision_overhead"]', source)
        self.assertIn('["cost_usd"] = JValue.CreateNull()', source)


class AutoGatewayRenderedContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = render()
        cls.on = cls.rendered["on"]
        cls.tree = ET.fromstring(cls.on)

    def test_off_exact_bytes(self):
        self.assertEqual(self.rendered["off"].encode(), self.rendered["old"].encode())
        self.assertNotIn("aiflux-auto", self.rendered["off"])

    def test_platform_snapshot_matches_backend_without_database_or_tenant_rows(self):
        from aiflux.auto_snapshot import defaults
        from aiflux.config import Settings
        snapshot = defaults(Settings(_env_file=None, environment="testing", local_auth_enabled=True,
            foundry_inventory_path=ROOT / "gateway/catalog/foundry-inventory-20261026.json"))
        gateway = json.loads(base64.b64decode(self.rendered["snapshot"]))
        self.assertEqual(gateway["version"], snapshot["version"])
        self.assertEqual(gateway["profiles"], snapshot["profiles"])
        self.assertEqual(gateway["candidates"], {c["id"]: c for c in snapshot["candidates"]})

    def test_all_thirteen_explicit_paths_cannot_enter_scoring_branch_when_auto_on(self):
        manifest = ROOT / "gateway/catalog/fireworks-candidate-routes.json"
        rendered = render([f"-var=route_manifest_path={manifest}", "-var=glm_enabled=true"])
        tree = ET.fromstring(rendered["on"])
        request = tree.find('.//send-request[@id="aiflux-auto-resolver"]')
        parents = {child: parent for parent in tree.iter() for child in parent}
        self.assertEqual(parents[request].tag, "when")
        self.assertEqual(parents[request].get("condition"), '@((bool)context.Variables["aiflux-auto"])')
        marker = tree.find('.//set-variable[@name="aiflux-auto"]')
        self.assertEqual(marker.get("value"), '@((string)context.Variables["aiflux-model"] == "auto")')
        for alias in rendered["aliases"]:
            self.assertNotEqual(alias, "auto")
            self.assertIn(f'== "{alias}"', rendered["on"])
        self.assertEqual(len(rendered["aliases"]), 13)
        self.assertEqual(len(tree.findall('.//set-body[@id="aiflux-auto-metadata"]')), 1)
        self.assertGreaterEqual(len(tree.findall("on-error/choose/when/return-response")), 1)
        self.assertNotIn('context.Subscription.Id !=', rendered["on"])
        self.assertNotIn("/internal/auto-routing/resolve", rendered["on"])
        self.assertEqual(len(tree.findall('.//send-request[@id="aiflux-auto-resolver"]')), 1)

    def test_direct_errors_always_fail_closed_and_scoring_token_is_subrequest_only(self):
        source = (POLICIES / "auto-resolve.xml.tftpl").read_text()
        self.assertIn('response.StatusCode != 200', source)
        self.assertIn('["fallback_used"] = false', source)
        self.assertNotIn("cache-", source)
        self.assertNotIn("<retry", source)
        self.assertNotIn('context.Request.Headers', source)
        self.assertIn('characters > 8000', source)
        tree = ET.fromstring("<root>" + source + "</root>")
        parents = {child: parent for parent in tree.iter() for child in parent}
        auth_headers = tree.findall('.//set-header[@name="Authorization"]')
        self.assertEqual(len(auth_headers), 1)
        self.assertEqual(parents[auth_headers[0]].tag, "send-request")

    def test_complete_thirteen_explicit_routes_off_is_exact_original(self):
        manifest = ROOT / "gateway/catalog/fireworks-candidate-routes.json"
        rendered = render([f"-var=route_manifest_path={manifest}", "-var=glm_enabled=true"])
        expected = {"gpt-5.6-luna", "gpt-6.1-sol", "gpt-5.4-mini", "gpt-4o",
            "DeepSeek-V4-Flash", "DeepSeek-V4-Pro", "Kimi-K2.7-Code", "grok-4.3",
            "grok-4-20-reasoning", "grok-4-1-fast-reasoning", "FW-GLM-5.3", "FW-MiniMax-M3", "glm-5.3"}
        self.assertEqual(set(rendered["aliases"]), expected)
        self.assertEqual(rendered["off"].encode(), rendered["old"].encode())
        self.assertNotIn("aiflux-auto", rendered["off"])
        for alias in expected:
            self.assertIn(f'== "{alias}"', rendered["off"])
        self.assertEqual(rendered["off"].count("<quota-by-key"), 1)
        self.assertEqual(rendered["off"].count("<llm-content-safety"), 3)

    def test_order_daily_admission_safety_pii_redacted_safety_selection_limits_backend(self):
        inbound = self.on.split("</inbound>")[0]
        positions = [
            inbound.index("<quota-by-key"), inbound.index("auto-admission:"),
            inbound.index("<llm-content-safety"), inbound.index('response-variable-name="aiflux-pii"'),
            inbound.rindex("<llm-content-safety"), inbound.index('id="aiflux-auto-resolver"'),
            inbound.index('<set-variable name="aiflux-model"', inbound.index('id="aiflux-auto-resolver"')),
            inbound.rindex('<rate-limit-by-key calls="60"'), inbound.index("<set-backend-service"),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(inbound.count("<quota-by-key"), 1)
        self.assertEqual(inbound.count("auto-admission:"), 1)
        self.assertEqual(inbound.count('id="aiflux-auto-resolver"'), 1)
        self.assertEqual(inbound.count("<llm-content-safety"), 2)
        self.assertEqual(self.on.count('window-size="1000"'), 1)

    def test_selected_model_limits_are_original_and_mutually_exclusive(self):
        limits = self.rendered["model_limits"]
        self.assertEqual(limits.count("<rate-limit-by-key"), 1)
        self.assertEqual(limits.count("<llm-token-limit"), 1)
        for key in ('"rpm:"', '"tpm:"', 'token-quota="10000"', 'tokens-per-minute="2048"'):
            self.assertIn(key, limits)
        inbound = self.tree.find("inbound")
        admission = inbound.find(".//choose/otherwise/rate-limit-by-key")
        self.assertIsNotNone(admission)
        selected = inbound.find('.//when[@condition=\'@((bool)context.Variables["aiflux-auto"])\']/llm-token-limit')
        self.assertIsNotNone(selected)
        self.assertEqual(len(inbound.findall(".//quota-by-key")), 1)
        self.assertEqual(len(inbound.findall(".//llm-token-limit")), 2)

    def test_only_auto_accepts_profiles_and_existing_strict_shape_survives(self):
        conditions = " ".join(node.get("condition", "") for node in self.tree.findall(".//when"))
        self.assertIn('(p.Name == "routing_profile" && body["model"] != null && body["model"].Type == JTokenType.String && (string)body["model"] == "auto")', conditions)
        self.assertIn('new [] { "balanced", "cost", "quality" }', conditions)
        self.assertIn('body["routing_profile"].Type != JTokenType.String', conditions)
        for unchanged in ('item["content"].Type != JTokenType.String', 'body["stream"].Type != JTokenType.Boolean',
                          '(bool)body["stream"]', "totalCharacters > 8000", "messages.Count > 25"):
            self.assertIn(unchanged, conditions)
        self.assertNotIn('p.Name == "tools"', conditions)
        self.assertEqual(set(self.rendered["candidates"]), CANDIDATES)
        # Resolver must require BOTH current manifest and six reviewed aliases.
        result = self.tree.find('.//set-variable[@name="aiflux-auto-result"]').get("value")
        self.assertIn('!((string)model == "gpt-5.6-luna")', result)
        for candidate in CANDIDATES:
            self.assertIn(f'(string)model == "{candidate}"', result)

    def test_metadata_after_output_safety_finops_uses_resolved_alias(self):
        outbound = self.on.split("<outbound>")[1].split("</outbound>")[0]
        self.assertLess(outbound.rindex("<llm-content-safety"), outbound.index('id="aiflux-auto-metadata"'))
        self.assertIn('counters["model"] = (string)context.Variables["aiflux-model"]', outbound)
        self.assertLess(outbound.index('name="aiflux-finops-usage"'), outbound.index('id="aiflux-auto-metadata"'))

    def test_six_candidate_mock_manifest_and_provider_dialects(self):
        # A temporary fixture is NOT a fresh accepted route inventory. Evaluate
        # only local composition; never enable a resource or query a deployment.
        routes = {
            alias: {"version": "test-only", "provider": "OpenAI",
                    "token_parameter": "max_tokens" if alias in {
                        "DeepSeek-V4-Flash", "Kimi-K2.7-Code"
                    } else "max_completion_tokens"}
            for alias in CANDIDATES | {"unreviewed-test-alias"}
        }
        with tempfile.TemporaryDirectory(prefix="auto-route-contract-") as temporary:
            fixture = Path(temporary) / "routes.json"
            fixture.write_text(json.dumps({
                "project_endpoint": "https://poc-ids-token-ex-foundry.services.ai.azure.com/api/projects/poc-ids-token-ex-foundry-project",
                "upstream_url": "https://poc-ids-token-ex-foundry.openai.azure.com/openai/v1",
                "routes": routes,
            }), encoding="utf-8")
            rendered = render([f"-var=route_manifest_path={fixture}"])
        tree = ET.fromstring(rendered["on"])
        inbound = rendered["on"].split("</inbound>")[0]
        self.assertEqual(inbound.count('id="aiflux-auto-resolver"'), 1)
        self.assertEqual(inbound.count("<quota-by-key"), 1)
        self.assertEqual(rendered["off"], rendered["old"])
        self.assertLess(inbound.index('id="aiflux-auto-resolver"'), inbound.index("<set-backend-service"))
        validator = tree.find('.//set-variable[@name="aiflux-auto-result"]').get("value")
        self.assertIn('!((string)model == "DeepSeek-V4-Flash"', validator)
        # A current manifest alias is still forbidden if not in the fixed six.
        checks = validator.split('var modelMaximum = 0;')[0]
        self.assertEqual(checks.count('(string)model == "unreviewed-test-alias"'), 1)
        rewrite = next(body.text for body in tree.findall(".//set-body")
                       if body.text and 'request.Remove("routing_profile")' in body.text)
        self.assertIn('if ((string)request["model"] == "DeepSeek-V4-Flash")', rewrite)
        self.assertIn('request.Remove("max_completion_tokens")', rewrite)


if __name__ == "__main__":
    unittest.main()