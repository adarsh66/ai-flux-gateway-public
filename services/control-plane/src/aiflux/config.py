import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIFLUX_", env_file=".env", extra="ignore")

    environment: Literal["development", "testing", "production"] = "development"
    database_url: str = ""
    entra_audience: str = ""
    entra_client_id: str = ""
    home_tenant_id: str = ""
    bootstrap_object_id: str = ""
    home_organization_name: str = "Singtel IDS"
    required_scope: str = "access_as_user"
    gateway_url: str = ""
    gateway_max_completion_tokens: int | None = Field(default=None, ge=1, le=100000)
    apim_resource_id: str = ""
    apim_product_id: str = "aiflux"
    gateway_settings_scopes: list[Literal["dev-openai", "dev-unified"]] = []
    gateway_controls_v2_enabled: bool = False
    gateway_protected_material_available: bool = False
    gateway_monthly_request_quota_available: bool = False
    gateway_safety_relaxation_allowed: bool = False
    gateway_enforcement_enabled: bool = False
    gateway_max_rpm: int = Field(default=2, ge=1, le=100000)
    gateway_initial_safety_threshold: int = Field(default=1, ge=0, le=7)
    log_workspace_id: str = ""
    catalog_path: Path = Path("gateway/catalog/models.json")
    catalog_configured: bool = False
    acme_challenge_enabled: bool = False
    acme_challenge_directory: Path = Path("/home/aiflux-acme-challenges")
    cors_origins: list[str] = []
    ingestion_overlap_minutes: int = 60
    ingestion_initial_days: int = 1
    ingestion_batch_minutes: int = 60
    ingestion_delay_minutes: int = 5
    ingestion_max_rows: int = 10000
    ingestion_start_at: datetime | None = None
    mise_validation_endpoint: str | None = None
    ledger_storage_account: str = ""
    ledger_table_name: str = "TurnstileLedger"
    model_routes_table_name: str = "ModelRoutes"
    eventhub_namespace: str = ""
    eventhub_name: str = "token-usage"
    decision_router_enabled: bool = True
    decision_router_endpoint: str = "/providers/microsoft/v1/systemone"
    decision_router_default_model: str = "gpt-5.4-mini"
    local_auth_enabled: bool = False
    local_jwt_secret: str = "turnstile-local-postgres-jwt-signing-secret-key-2026"
    bootstrap_admin_email: str = "admin@tokenx-ids.com"
    bootstrap_admin_password: str = "tokenx-admin"
    bootstrap_customer_email: str = "developer@caldova.com"
    bootstrap_customer_password: str = "caldova-pass"
    bootstrap_customer_org: str = "Caldova"
    upstream_apim_url: str = ""
    upstream_apim_key: str = ""

    @model_validator(mode="after")
    def populate_turnstile_env_fallbacks(self) -> "Settings":
        if not self.ledger_storage_account and os.environ.get("LEDGER_STORAGE_ACCOUNT"):
            self.ledger_storage_account = os.environ["LEDGER_STORAGE_ACCOUNT"]
        if os.environ.get("LEDGER_TABLE_NAME"):
            self.ledger_table_name = os.environ["LEDGER_TABLE_NAME"]
        if not self.eventhub_namespace and os.environ.get("EVENTHUB_NAMESPACE"):
            self.eventhub_namespace = os.environ["EVENTHUB_NAMESPACE"]
        if os.environ.get("EVENTHUB_NAME"):
            self.eventhub_name = os.environ["EVENTHUB_NAME"]
        if not self.upstream_apim_url and os.environ.get("APIM_GATEWAY_URL"):
            self.upstream_apim_url = os.environ["APIM_GATEWAY_URL"]
        if not self.upstream_apim_key and os.environ.get("APIM_PROBE_SUBSCRIPTION_KEY"):
            self.upstream_apim_key = os.environ["APIM_PROBE_SUBSCRIPTION_KEY"]
        is_pg = self.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
        if is_pg and self.environment != "production":
            self.local_auth_enabled = True
        if self.local_auth_enabled and self.database_url:
            if not self.home_tenant_id:
                self.home_tenant_id = "00000000-0000-0000-0000-000000000001"
            if not self.entra_audience:
                self.entra_audience = "local://turnstile-postgres-auth"
        return self

    def identity_errors(self) -> list[str]:
        errors = []
        for name in ("database_url", "entra_audience", "home_tenant_id"):
            if not getattr(self, name):
                errors.append(f"{name} is required")
        if self.home_tenant_id:
            try:
                UUID(self.home_tenant_id)
            except ValueError:
                errors.append("home_tenant_id must be an Entra tenant UUID")
        if self.entra_client_id:
            try:
                UUID(self.entra_client_id)
            except ValueError:
                errors.append("entra_client_id must be an Entra application UUID")
        if self.mise_validation_endpoint:
            try:
                parsed = urlparse(self.mise_validation_endpoint)
                if parsed.scheme not in ("http", "https"):
                    errors.append("mise_validation_endpoint must use http or https")
                hostname = parsed.hostname or ""
                if hostname not in ("127.0.0.1", "localhost", "::1"):
                    errors.append("mise_validation_endpoint must be a loopback address")
                if not parsed.path.rstrip("/").endswith("/Validate"):
                    errors.append("mise_validation_endpoint must target the /Validate path")
            except Exception:
                errors.append("mise_validation_endpoint must be a valid URL")
        is_postgres = self.database_url.startswith(("postgresql://", "postgresql+psycopg://"))
        is_mssql = self.database_url.startswith("mssql+pyodbc://")
        if self.environment == "production" and not (is_mssql or is_postgres):
            errors.append("production requires passwordless Azure SQL or Azure PostgreSQL")
        if self.environment == "production" and is_mssql:
            url = make_url(self.database_url)
            if url.username or url.password:
                errors.append("production SQL credentials must use managed identity")
            if "odbc_connect" in url.query:
                errors.append(
                    "production SQL must use explicit URL parameters, not an opaque connection string"
                )
            if str(url.query.get("Encrypt", "yes")).lower() not in ("yes", "true", "mandatory", "strict"):
                errors.append("production SQL must encrypt connections")
            if str(url.query.get("TrustServerCertificate", "no")).lower() not in ("no", "false"):
                errors.append("production SQL must validate the server certificate")
        if self.environment == "production" and is_postgres:
            url = make_url(self.database_url)
            if url.password:
                errors.append("production PostgreSQL credentials must use managed identity")
            if str(url.query.get("sslmode", "require")).lower() not in (
                "require", "verify-ca", "verify-full",
            ):
                errors.append("production PostgreSQL must encrypt connections with sslmode=require")
        return errors


@lru_cache
def get_settings() -> Settings:
    return Settings()
