"""Credential-free external evidence. Never relax Foundry parent verification.

This is an operator release artifact, not runtime discovery or an admin URL input.
Absent, stale or invalid external evidence disables only external routes.
"""
from datetime import UTC, datetime
import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from aiflux.catalog import Catalog, ModelEntry
from aiflux.config import Settings
from aiflux.foundry_inventory import EvidenceModel, FoundryInventory, RouteEvidence

GLM_UPSTREAM = "https://api-ap-southeast-1.modelarts-maas.com/v1"
GATEWAY = "https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1"


class ExternalMetadataRenewal(EvidenceModel):
    """Operator metadata attestation, never a new smoke or credential-health test.

    Like Foundry deployment-read renewal, this preserves historical functional
    acceptance and separately bounds the age of a real control-plane read.
    The release collector checks the complete policy/backend predecessor and the
    fixed internal secret reference without listValue, keys or provider traffic.
    """
    kind: Literal["unchanged_apim_metadata"]
    observed_at: datetime
    historical_acceptance_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    backend_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference_metadata_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    named_value_resource_id: str
    secret_storage: Literal["apim_internal_secret"]
    fresh_credential_health_verified: Literal[False]
    smoke_repeated: Literal[False]


def historical_acceptance_sha256(route: "ExternalRoute") -> str:
    value = route.model_dump(mode="json", exclude={"metadata_renewal"})
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ExternalRoute(EvidenceModel):
    alias: Literal["glm-5.3"]
    provider: Literal["ModelArts"]
    backend_model: Literal["glm-5.3"]
    upstream_url: Literal["https://api-ap-southeast-1.modelarts-maas.com/v1"]
    endpoint_url: Literal["https://poc-ids-token-ex-apim.azure-api.net/dev/llm/v1"]
    api_format: Literal["openai-chat-completions"]
    upstream_token_parameter: Literal["max_completion_tokens"]
    capabilities: list[Literal["chat"]] = Field(min_length=1, max_length=1)
    max_completion_tokens: Literal[1024]
    gateway_validated: bool = False
    credential_healthy: bool = False
    probe_status: Literal[200] | None = None
    probe_completion_tokens: int | None = Field(default=None, ge=1, le=200)
    probe_prompt_tokens: int | None = Field(default=None, ge=0)
    probe_total_tokens: int | None = Field(default=None, ge=1)
    assistant_nonempty: bool = False
    verified_at: datetime | None = None
    pricing_status: Literal["unknown"] = "unknown"
    metadata_renewal: ExternalMetadataRenewal | None = None

    @model_validator(mode="after")
    def accepted_requires_evidence(self) -> "ExternalRoute":
        if self.gateway_validated and not (
            self.credential_healthy and self.probe_status == 200 and self.assistant_nonempty
            and self.verified_at is not None and self.verified_at.tzinfo is not None
            and self.probe_completion_tokens is not None and self.probe_prompt_tokens is not None
            and self.probe_total_tokens == self.probe_completion_tokens + self.probe_prompt_tokens
        ):
            raise ValueError("External acceptance requires a metered, nonempty bounded gateway probe")
        renewal = self.metadata_renewal
        if renewal is not None:
            expected_reference = (
                "/subscriptions/aa28274d-fea0-46d4-b9c8-30f3ef0a0e52/resourceGroups/"
                "IDS-TOKEN-EXCHANGE-POC/providers/Microsoft.ApiManagement/service/"
                "poc-ids-token-ex-apim/namedValues/aiflux-glm-5-3-api-key")
            if not (self.gateway_validated and self.verified_at is not None
                    and renewal.observed_at.tzinfo is not None
                    and renewal.observed_at >= self.verified_at
                    and renewal.named_value_resource_id == expected_reference
                    and renewal.historical_acceptance_sha256 == historical_acceptance_sha256(self)):
                raise ValueError("Metadata renewal must bind unchanged historical acceptance and exact reference")
        return self

    def accepted(self, settings: Settings) -> bool:
        if not self.gateway_validated or self.verified_at is None:
            return False
        now = datetime.now(UTC)
        if self.verified_at > now:
            return False
        freshness_at = self.metadata_renewal.observed_at if self.metadata_renewal else self.verified_at
        age = (now - freshness_at).total_seconds()
        return 0 <= age <= settings.foundry_inventory_max_age_seconds


class ExternalInventory(EvidenceModel):
    schema_version: Literal[1]
    routes: list[ExternalRoute]

    @model_validator(mode="after")
    def unique_aliases(self) -> "ExternalInventory":
        if len({r.alias for r in self.routes}) != len(self.routes):
            raise ValueError("Duplicate external aliases")
        return self


class AcceptedInventory:
    """Provider boundary shared by models, garden, playground, sync and admin."""

    def __init__(self, foundry: FoundryInventory, external: ExternalInventory, settings: Settings):
        self.foundry, self.external, self.settings = foundry, external, settings
        self.verified_at = foundry.verified_at

    @classmethod
    def load(cls, settings: Settings) -> "AcceptedInventory":
        foundry = FoundryInventory.load(settings)  # All original parent checks remain mandatory.
        external = ExternalInventory(schema_version=1, routes=[])
        if settings.external_inventory_path is not None:
            try:
                candidate = ExternalInventory.model_validate_json(
                    settings.external_inventory_path.read_text(encoding="utf-8"))
                if {r.alias for r in candidate.routes} & {r.alias for r in foundry.routes}:
                    raise ValueError("Alias collision across providers")
                external = candidate
            except (OSError, ValueError, TypeError):
                pass  # Fail closed for GLM only; never replace working Foundry routes.
        return cls(foundry, external, settings)

    def route(self, alias: str) -> RouteEvidence | ExternalRoute | None:
        route = self.foundry.route(alias)
        if route is not None:
            return route
        return next((r for r in self.external.routes if r.alias == alias and r.accepted(self.settings)), None)

    def provider(self, alias: str) -> str:
        route = self.route(alias)
        if isinstance(route, ExternalRoute):
            return route.provider
        if route is None:
            raise ValueError("Unaccepted route")
        return next(d.model_format for d in self.foundry.deployments
                    if d.id.lower() == route.deployment_id.lower())

    def matches(self, alias: str, backend_model: str, endpoint_urls: list[str]) -> bool:
        route = self.route(alias)
        return bool(route and backend_model == route.backend_model and endpoint_urls
                    and all(url.rstrip("/") == route.endpoint_url.rstrip("/") for url in endpoint_urls))

    def matches_catalog_model(self, model: ModelEntry) -> bool:
        route = self.route(model.id)
        return bool(route and self.matches(model.id, model.backend_model,
                    [b.url for b in model.backends] if model.backends else [route.endpoint_url])
                    and all(not b.model or b.model == model.backend_model for b in model.backends))

    def accepted_aliases(self, settings: Settings) -> set[str]:
        aliases = self.foundry.accepted_aliases(settings)
        if settings.catalog_configured:
            aliases |= {m.id for m in Catalog.load(settings.catalog_path).models
                        if m.enabled and not m.placeholder and "chat" in m.capabilities
                        and self.matches_catalog_model(m)}
        elif settings.local_auth_enabled:
            aliases |= {r.alias for r in self.external.routes if r.accepted(settings)}
        return aliases

    def discovery(self) -> list[dict]:
        return self.foundry.discovery() + [{
            "id": r.alias, "provider": r.provider, "model_name": r.backend_model,
            "model_version": "Unverified", "role": "chat",
            "status": "gateway-verified" if r.accepted(self.settings) else "pending-verification",
            "chat_selectable": r.accepted(self.settings), "pricing_status": "unknown",
            "credential_healthy": r.credential_healthy if r.accepted(self.settings) else False,
            "credential_health_verified_at": r.verified_at,
            "metadata_verified_at": r.metadata_renewal.observed_at if r.metadata_renewal else None,
            "fresh_credential_health_verified": False if r.metadata_renewal else r.accepted(self.settings),
            "limitation": (
                "Historical metered credential health at " + r.verified_at.isoformat()
                + "; unchanged binding metadata verified at " + r.metadata_renewal.observed_at.isoformat()
                + "; current credential health not tested. "
                if r.metadata_renewal and r.verified_at else ""
            ) + "External ModelArts processing; PII redaction is best-effort, not anonymization.",
        } for r in self.external.routes]