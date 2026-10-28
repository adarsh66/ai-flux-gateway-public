"""No Azure calls, secrets, user-IP discovery or real ingress changes."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.deployment import admin_ingress as ingress
from scripts.deployment import run_private_sql as runner

SITE = ingress.portals.site("admin")
CIDRS = ["8.8.8.8/32", "2606:4700:4700::1111/128"]  # Fixtures, never operator defaults.
ROOT = Path(__file__).resolve().parents[2]


class FakeArm:
    def __init__(self, fail_at=None):
        self.app = {"properties": {"publicNetworkAccess": "Disabled", "httpsOnly": True,
                                   "virtualNetworkSubnetId": "preserve-existing"}}
        self.config = {"linuxFxVersion": "preserve-image", **ingress.restriction_properties([])}
        self.calls = []
        self.fail_at = fail_at

    def get(self, resource, version):
        self.calls.append(("GET", resource))
        if resource.endswith("/config/web"):
            result = deepcopy(self.config)
            if self.fail_at == "readback":
                result["scmIpSecurityRestrictionsUseMain"] = True
            if self.fail_at == "post_enable" and self.app["properties"]["publicNetworkAccess"] == "Enabled":
                result["ipSecurityRestrictionsDefaultAction"] = "Allow"
            return {"properties": result}
        return deepcopy(self.app)

    def request(self, method, resource, version, body):
        self.calls.append((method, resource, deepcopy(body)))
        assert resource in (SITE, SITE + "/config/web")
        props = body["properties"]
        if resource.endswith("/config/web"):
            if self.fail_at == "write":
                raise RuntimeError("not logged")
            self.config.update(props)
        else:
            if props["publicNetworkAccess"] == "Enabled":
                # Simulate success-at-server then timeout-at-client too.
                ingress.verify_rules(self.config, CIDRS)
                self.app["properties"].update(props)
                if self.fail_at == "enable":
                    raise TimeoutError
            self.app["properties"].update(props)


@pytest.mark.parametrize("values", [[], [""], ["8.8.8.8"], ["0.0.0.0/0"], ["::/0"],
    ["10.1.1.1/32"], ["127.0.0.1/32"], ["100.64.0.1/32"], ["169.254.169.254/32"],
    ["192.0.2.1/32"], ["198.51.100.0/24"], ["203.0.113.1/32"], ["224.0.0.1/32"],
    ["240.0.0.1/32"], ["8.8.8.9/24"], ["8.8.8.8/32,1.1.1.1/32"], ["AzureCloud"],
    ["2001:db8::1/128"], ["fc00::/7"], ["fe80::/10"], ["ff00::/8"],
    ["::ffff:8.8.8.8/128"], ["2606:4700::%eth0/32"], ["8.0.0.0/6"],
    ["2000::/3"], ["8.8.8.8/32"] * 501, [None]])
def test_bad_or_missing_input_has_no_azure_calls(values):
    arm = Mock()
    with pytest.raises(runner.RunnerError):
        ingress.configure_ingress(arm, SITE, values)
    assert not arm.mock_calls


def test_valid_public_cidrs_deduplicated_without_widening():
    assert ingress.public_cidrs(CIDRS + CIDRS) == CIDRS


def test_only_site_resources_accepted():
    arm = Mock()
    with pytest.raises(runner.RunnerError, match="site_resource_required"):
        ingress.configure_ingress(arm, SITE + "/slots/production", CIDRS)
    assert not arm.mock_calls


def test_deny_verified_before_enable_and_unrelated_configuration_preserved():
    arm = FakeArm()
    result = ingress.configure_ingress(arm, SITE, CIDRS)
    assert result["scm_allows"] == 0
    writes = [c for c in arm.calls if c[0] == "PATCH"]
    assert [c[1] for c in writes] == [SITE, SITE + "/config/web", SITE]
    assert writes[0][2]["properties"] == {"publicNetworkAccess": "Disabled"}
    assert writes[-1][2]["properties"] == {"publicNetworkAccess": "Enabled"}
    assert arm.calls.index(writes[-1]) > next(i for i, c in enumerate(arm.calls) if c == ("GET", SITE + "/config/web"))
    assert arm.config["linuxFxVersion"] == "preserve-image"
    assert arm.app["properties"]["virtualNetworkSubnetId"] == "preserve-existing"
    ingress.verify_rules(arm.config, CIDRS)
    # Reusable operation is idempotent, closing the site first on every run.
    ingress.configure_ingress(arm, SITE, CIDRS)


@pytest.mark.parametrize("stage", ["write", "readback", "enable", "post_enable"])
def test_any_write_or_verification_failure_disables_public(stage):
    arm = FakeArm(stage)
    with pytest.raises(runner.RunnerError, match="ingress_failed_public_disabled"):
        ingress.configure_ingress(arm, SITE, CIDRS)
    assert arm.app["properties"]["publicNetworkAccess"] == "Disabled"
    assert arm.calls[-1] == ("GET", SITE)
    if stage in ("write", "readback"):
        assert not any(c[0] == "PATCH" and c[2]["properties"].get("publicNetworkAccess") == "Enabled" for c in arm.calls)


def test_unconfirmed_rollback_is_not_reported_as_disabled():
    arm = FakeArm()
    original = arm.request
    def fail(method, resource, version, body):
        if resource.endswith("/config/web"):
            arm.fail_at = "readback"
        if resource == SITE and body["properties"].get("publicNetworkAccess") == "Disabled" and arm.fail_at:
            raise RuntimeError
        return original(method, resource, version, body)
    arm.request = fail
    with pytest.raises(runner.RunnerError, match="ingress_failed_rollback_unconfirmed"):
        ingress.configure_ingress(arm, SITE, CIDRS)


@pytest.mark.parametrize("mutation", ["extra_main", "extra_scm", "inherit", "default", "selector", "priority"])
def test_readback_rejects_bypass_rules(mutation):
    config = ingress.restriction_properties(CIDRS)
    if mutation == "extra_main":
        config["ipSecurityRestrictions"].append({"action": "Allow", "ipAddress": "Any"})
    elif mutation == "extra_scm":
        config["scmIpSecurityRestrictions"].append({"action": "Allow", "ipAddress": CIDRS[0]})
    elif mutation == "inherit":
        config["scmIpSecurityRestrictionsUseMain"] = True
    elif mutation == "default":
        config["ipSecurityRestrictionsDefaultAction"] = "Allow"
    elif mutation == "selector":
        config["ipSecurityRestrictions"][0]["tag"] = "ServiceTag"
    else:
        config["ipSecurityRestrictions"][0]["priority"] = 999
    with pytest.raises(runner.RunnerError):
        ingress.verify_rules(config, CIDRS)


def test_admin_proxy_fixed_tls_authorization_forwarding_and_customer_unchanged():
    admin = (ROOT / "apps/admin-portal/nginx.conf.template").read_text()
    customer = (ROOT / "apps/customer-portal/nginx.conf.template").read_text()
    assert "location ^~ /api/" in admin
    assert "proxy_pass https://poc-ids-token-ex-api.azurewebsites.net;" in admin
    assert "proxy_pass $" not in admin
    assert "proxy_ssl_verify on;" in admin and "proxy_ssl_server_name on;" in admin
    assert "proxy_ssl_name poc-ids-token-ex-api.azurewebsites.net;" in admin
    assert 'proxy_set_header Authorization ""' not in admin
    assert "add_header Cache-Control \"no-store\" always;" in admin
    assert "location ^~ /api/admin/ { return 403; }" not in admin
    assert "location ^~ /api/admin/ { return 403; }" in customer
    dockerfile = (ROOT / "apps/admin-portal/Dockerfile").read_text()
    assert 'RUN test "$VITE_PORTAL_MODE" != "sql" || test "$VITE_CONTROL_API_URL" = "/api"' in dockerfile
    script = (ROOT / "scripts/deploy-existing-apps.ps1").read_text()
    assert 'if ($target.Name -eq $AdminApp) { $portalApiBase = "/api" }' in script


def test_cli_missing_allowlist_fails_before_authentication(monkeypatch):
    monkeypatch.setattr("sys.argv", ["admin_ingress", "--apply"])
    cli = Mock()
    monkeypatch.setattr(runner, "cli", cli)
    with pytest.raises(SystemExit) as exc:
        ingress.main()
    assert exc.value.code == 2
    cli.assert_not_called()


def test_cli_input_validation_does_not_authenticate_or_apply(monkeypatch):
    monkeypatch.setattr("sys.argv", ["admin_ingress", "--allow-cidr", CIDRS[0]])
    cli = Mock()
    monkeypatch.setattr(runner, "cli", cli)
    assert ingress.main() == 0
    cli.assert_not_called()


@pytest.mark.parametrize("digest", [None, ingress.LEGACY_ADMIN, "latest", "sha256:bad"])
def test_cli_apply_requires_explicit_nonlegacy_release_before_auth(monkeypatch, digest):
    argv = ["admin_ingress", "--allow-cidr", CIDRS[0], "--apply"]
    if digest is not None:
        argv += ["--admin-image-digest", digest]
    monkeypatch.setattr("sys.argv", argv)
    cli = Mock()
    monkeypatch.setattr(runner, "cli", cli)
    assert ingress.main() == 1
    cli.assert_not_called()


def test_interrupt_after_enable_also_disables_public():
    arm = FakeArm()
    original = arm.request
    def interrupt(method, resource, version, body):
        original(method, resource, version, body)
        if body["properties"].get("publicNetworkAccess") == "Enabled":
            raise KeyboardInterrupt
    arm.request = interrupt
    with pytest.raises(runner.RunnerError, match="ingress_failed_public_disabled"):
        ingress.configure_ingress(arm, SITE, CIDRS)
    assert arm.app["properties"]["publicNetworkAccess"] == "Disabled"


def test_https_required_and_failure_never_enables():
    arm = FakeArm()
    arm.app["properties"]["httpsOnly"] = False
    with pytest.raises(runner.RunnerError, match="ingress_failed_public_disabled"):
        ingress.configure_ingress(arm, SITE, CIDRS)
    assert not any(c[0] == "PATCH" and c[2]["properties"].get("publicNetworkAccess") == "Enabled" for c in arm.calls)