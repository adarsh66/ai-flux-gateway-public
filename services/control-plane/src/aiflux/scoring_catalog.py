"""Presentation-only scoring identity; never a chat alias or an Auto candidate.

Deployment verification is not a live authorization/response probe. No catalog
read writes model economics, discovers resources, or invokes the scorer.
"""
import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
from typing import Any
from urllib.parse import urlsplit

from aiflux.config import Settings
from aiflux.external_inventory import AcceptedInventory
from aiflux.schemas import ModelGardenItemOutput

MODEL_ID = "Decision-1"
DISPLAY_NAME = "Microsoft Decision-1"


def is_scoring_model(model: str) -> bool:
    """Reserve both deployment and official model names from chat promotion."""
    return model.casefold() in {MODEL_ID.casefold(), "microsoft-decision-1"}


@lru_cache(maxsize=1)
def scoring_manifest() -> dict[str, Any]:
    """Separate byte-bound tariff; deliberately absent from the chat manifest."""
    raw = files("aiflux").joinpath("pricing/decision1-scoring-20261031.json").read_bytes()
    data = json.loads(raw)
    rate = data["rate"]
    if (rate["model"] != MODEL_ID or rate["model_kind"] != "scoring"
            or rate["billing_dimensions"] != ["input"]
            or any(field in rate for field in ("output", "cached", "write"))):
        raise ValueError("Invalid scoring tariff dimensions")
    data["sha256"] = hashlib.sha256(raw).hexdigest()
    return data


def scoring_descriptor() -> dict[str, Any]:
    """Immutable-source rate scope (not an assertion of deployment availability)."""
    data = scoring_manifest()
    return {**deepcopy(data["rate"]), "applicable_from": data["applicable_from"]}


def scoring_metadata(settings: Settings, inventory: AcceptedInventory) -> dict[str, Any]:
    """Tri-state availability from joined inventory/Settings, not SQL or Auto flags.

    None means absent/ambiguous/incompatible evidence; False means explicitly
    inactive or a mismatched configured scoring endpoint. Missing deployment
    state stays null in provenance; successful provisioning follows the existing
    Foundry inventory's optional deployment-state contract.
    """
    result: dict[str, Any] = {
        "scoring_available": None, "endpoint_url": "", "deployment_sku": None,
        "deployment_state": None,
    }
    foundry = inventory.foundry
    matches = [d for d in foundry.deployments if d.name == MODEL_ID]
    if len(matches) != 1:
        return result
    deployment = matches[0]
    rate = scoring_descriptor()
    if (deployment.id.lower() != (foundry.account_resource_id + "/deployments/" + MODEL_ID).lower()
            or deployment.model_name != rate["deployment_model"]
            or deployment.model_version != rate["model_version"]
            or deployment.model_format != rate["provider"]
            or not deployment.decision or deployment.chat_completion
            or foundry.project_endpoint != settings.foundry_project_endpoint.rstrip("/")
            or foundry.project_resource_id.lower() != settings.foundry_project_resource_id.lower()):
        return result
    project = urlsplit(foundry.project_endpoint)
    endpoint = f"https://{project.hostname}/providers/microsoft/v1/systemone"
    configured = settings.decision_router_endpoint.rstrip("/")
    available = None
    if (project.scheme != "https" or not project.hostname
            or configured not in (endpoint, "/providers/microsoft/v1/systemone")):
        available = False
    elif (deployment.capacity <= 0
            or deployment.provisioning_state in ("Failed", "Canceled", "Deleting", "Creating", "Updating")
            or deployment.deployment_state in ("Inactive", "Disabled", "Failed", "Deleted")):
        available = False
    elif (deployment.provisioning_state == "Succeeded"
            and deployment.deployment_state in (None, "Active", "Succeeded")):
        available = True
    result.update(
        endpoint_url=endpoint, deployment_sku=deployment.sku,
        deployment_state=deployment.deployment_state,
        scoring_available=available,
    )
    return result


def scoring_scope(settings: Settings, inventory: AcceptedInventory) -> dict[str, Any] | None:
    """Return the tariff only for deployment-verified scoring evidence."""
    if scoring_metadata(settings, inventory)["scoring_available"] is True:
        return scoring_descriptor()
    return None


def scoring_item(
    settings: Settings, inventory: AcceptedInventory, existing: ModelGardenItemOutput | None = None,
) -> ModelGardenItemOutput:
    """Overlay a DTO or create one without inserting/updating a model or price.

    Legacy economic fields are suppressed in the scorer's presentation, never
    changed in storage. Unknown deployment location/context is not guessed.
    """
    metadata = scoring_metadata(settings, inventory)
    fields: dict[str, Any] = dict(
        id=MODEL_ID, display_name=DISPLAY_NAME, model_kind="scoring",
        scoring_available=metadata["scoring_available"], provider="Microsoft", vendor="Microsoft",
        region="unknown", backend_model=MODEL_ID, endpoint_url=metadata["endpoint_url"],
        context_window=None, max_completion_tokens=0, input_per_million=None,
        output_per_million=None, cached_input_per_million=None, currency="USD",
        capabilities=["scoring"], enabled=False, coming_soon=False, content_safety_enabled=False,
        description="Scoring-only deployment; not a chat model or an Auto completion candidate. "
                    "Availability reflects deployment evidence, not a live authorization test.",
        display_price=None,
    )
    if existing is not None:
        return existing.model_copy(update=fields)
    return ModelGardenItemOutput(**fields)