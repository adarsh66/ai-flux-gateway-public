"""Fail-closed intersection of operator-verified deployments and accepted routes.

No discovery/catalog API, seeded SQL row, or connection is deployment evidence.
The snapshot is public metadata, refreshed by an authorized release operator; the
runtime does not acquire management-plane permissions or fall back on read failure.
"""

import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aiflux.catalog import Catalog, ModelEntry
from aiflux.config import Settings


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeploymentEvidence(EvidenceModel):
    id: str
    name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    model_format: str = Field(min_length=1)
    provisioning_state: str
    deployment_state: str | None = None
    capacity: int = Field(ge=0)
    chat_completion: bool
    decision: bool = False
    sku: str | None = None


class RouteEvidence(EvidenceModel):
    alias: str = Field(min_length=1)
    deployment_id: str
    backend_model: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    endpoint_url: str
    api_format: Literal["openai-chat-completions"]
    capabilities: list[str]
    max_completion_tokens: int = Field(ge=1)
    gateway_validated: bool = False
    upstream_token_parameter: Literal["max_completion_tokens", "max_tokens"] = "max_completion_tokens"
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None
    rejection_reason: str | None = None
    expires_at: datetime | None = None


class FoundryInventory(EvidenceModel):
    schema_version: Literal[1]
    verified_at: datetime
    project_endpoint: str
    project_resource_id: str
    account_resource_id: str
    account_read: Literal["Succeeded"]
    project_read: Literal["Succeeded"]
    connections_read: Literal["Succeeded"]
    connection_ids: list[str]
    project_deployments_read: Literal["Succeeded", "PermissionDenied"]
    deployments: list[DeploymentEvidence]
    routes: list[RouteEvidence]

    @classmethod
    def load(cls, settings: Settings) -> "FoundryInventory":
        try:
            if settings.foundry_inventory_path is None:
                raise ValueError("missing inventory")
            data = cls.model_validate_json(settings.foundry_inventory_path.read_text(encoding="utf-8"))
            age = (datetime.now(UTC) - data.verified_at).total_seconds()
            if not 0 <= age <= settings.foundry_inventory_max_age_seconds:
                raise ValueError("expired inventory")
            if data.project_endpoint != settings.foundry_project_endpoint.rstrip("/"):
                raise ValueError("wrong project endpoint")
            if data.project_resource_id.lower() != settings.foundry_project_resource_id.lower():
                raise ValueError("wrong project resource")
            account, separator, project = data.project_resource_id.rpartition("/projects/")
            if not separator or not project or account.lower() != data.account_resource_id.lower():
                raise ValueError("wrong parent account")
            if not re.fullmatch(
                r"/subscriptions/[0-9a-fA-F-]{36}/resourceGroups/[^/]+/providers/"
                r"Microsoft.CognitiveServices/accounts/[^/]+", account, re.IGNORECASE
            ):
                raise ValueError("invalid account resource ID")
            account_name = account.rsplit("/", 1)[-1].lower()
            expected_endpoint = f"https://{account_name}.services.ai.azure.com/api/projects/{project}"
            if data.project_endpoint != expected_endpoint:
                raise ValueError("resource and endpoint mismatch")
            # Connected accounts require their own joined deployment evidence. This
            # version deliberately supports only the verified project's parent.
            if data.connection_ids:
                raise ValueError("connected inventory requires explicit scope verification")
            ids = [d.id.lower() for d in data.deployments]
            if len(ids) != len(set(ids)) or len({d.name for d in data.deployments}) != len(ids):
                raise ValueError("duplicate deployments")
            if len({r.alias for r in data.routes}) != len(data.routes):
                raise ValueError("duplicate route aliases")
            for deployment in data.deployments:
                expected = data.account_resource_id + "/deployments/" + deployment.name
                if deployment.id.lower() != expected.lower():
                    raise ValueError("deployment outside parent account")
            return data
        except (OSError, ValueError, TypeError, ValidationError) as exc:
            raise HTTPException(503, "Verified Foundry deployment inventory is unavailable or expired") from exc

    def route(self, alias: str) -> RouteEvidence | None:
        route = next((r for r in self.routes if r.alias == alias and r.gateway_validated), None)
        if route is None:
            return None
        if route.expires_at is not None and (route.expires_at.tzinfo is None or datetime.now(UTC) >= route.expires_at):
            return None
        deployment = next((d for d in self.deployments if d.id.lower() == route.deployment_id.lower()), None)
        if (
            deployment is None
            or deployment.provisioning_state != "Succeeded"
            or deployment.deployment_state not in (None, "Active", "Succeeded")
            or deployment.capacity <= 0
            or not deployment.chat_completion
            or route.backend_model != deployment.name
            or route.model_name != deployment.model_name
            or route.model_version != deployment.model_version
            or "chat" not in route.capabilities
        ):
            return None
        endpoint = urlsplit(route.endpoint_url)
        if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
            return None
        if endpoint.query or endpoint.fragment:
            return None
        return route

    def discovery(self) -> list[dict]:
        """Public deployment status, never a grant of chat or router access."""
        items = []
        for deployment in self.deployments:
            active = (deployment.provisioning_state == "Succeeded"
                      and deployment.deployment_state in (None, "Active", "Succeeded")
                      and deployment.capacity > 0)
            accepted = self.route(deployment.name)
            candidate = next((r for r in self.routes if r.alias == deployment.name), None)
            role = "chat" if deployment.chat_completion else "routing-only" if deployment.decision else "unsupported"
            items.append({
                "id": deployment.name, "provider": deployment.model_format,
                "model_name": deployment.model_name, "model_version": deployment.model_version,
                "role": role, "status": "inactive" if not active else
                "gateway-verified" if accepted else "integration-unavailable" if role != "chat" else "pending-verification",
                "chat_selectable": bool(active and accepted), "pricing_status": "unknown",
                "limitation": candidate.rejection_reason if candidate else None,
            })
        return items

    def matches(self, alias: str, backend_model: str, endpoint_urls: list[str]) -> bool:
        route = self.route(alias)
        return bool(
            route
            and backend_model == route.backend_model
            and endpoint_urls
            and all(url.rstrip("/") == route.endpoint_url.rstrip("/") for url in endpoint_urls)
        )

    def accepted_aliases(self, settings: Settings) -> set[str]:
        """Use the same accepted metadata source for garden and router as /models."""
        if not settings.catalog_configured:
            return {r.alias for r in self.routes if self.route(r.alias)} if settings.local_auth_enabled else set()
        try:
            catalog = Catalog.load(settings.catalog_path)
        except (OSError, ValueError) as exc:
            raise HTTPException(503, "Model catalog is unavailable") from exc
        return {
            model.id for model in catalog.models
            if model.enabled and not model.placeholder and "chat" in model.capabilities
            and self.matches_catalog_model(model)
        }

    def matches_catalog_model(self, model: ModelEntry) -> bool:
        route = self.route(model.id)
        if route is None:
            return False
        # A catalog without a pool uses its explicit accepted inventory binding.
        # If it defines a pool, every member must match that binding exactly.
        urls = [backend.url for backend in model.backends] if model.backends else [route.endpoint_url]
        return self.matches(model.id, model.backend_model, urls) and all(
            not backend.model or backend.model == model.backend_model for backend in model.backends
        )