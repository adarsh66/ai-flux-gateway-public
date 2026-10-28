"""Prevent a successful SPA build from removing authenticated API transport."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("portal", ["admin", "customer"])
def test_existing_private_api_proxy_is_fixed_tls_verified_and_not_spa(portal):
    template = (ROOT / f"apps/{portal}-portal/nginx.conf.template").read_text()
    assert "location ^~ /api/ {" in template
    block = template.split("location ^~ /api/ {", 1)[1].split("}", 1)[0]
    assert "proxy_pass https://poc-ids-token-ex-api.azurewebsites.net;" in block
    assert "proxy_pass $" not in block
    assert "proxy_set_header Host poc-ids-token-ex-api.azurewebsites.net;" in block
    assert "proxy_ssl_server_name on;" in block
    assert "proxy_ssl_name poc-ids-token-ex-api.azurewebsites.net;" in block
    assert "proxy_ssl_verify on;" in block
    assert "proxy_ssl_verify_depth 5;" in block
    assert "proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;" in block
    assert 'proxy_set_header Authorization ""' not in block
    assert 'add_header Cache-Control "no-store" always;' in block
    assert "try_files" not in block


def test_customer_denies_admin_api_and_admin_redirect_preserves_public_https():
    customer = (ROOT / "apps/customer-portal/nginx.conf.template").read_text()
    admin = (ROOT / "apps/admin-portal/nginx.conf.template").read_text()
    assert "location ^~ /api/admin/ { return 403; }" in customer
    assert "location ^~ /api/admin/ { return 403; }" not in admin
    assert "absolute_redirect off;" in admin