"""Fixed-scope ARM transport. Never retrieve named-value secret values.

Ordinary namedValues GET omits secret content. Never use listSecrets. Only the
filtered metadata below can leave this module; HTTP bodies/errors are not logged.
"""
from datetime import UTC, datetime
import logging
import os

import requests
from azure.identity import AzureCliCredential

from scripts.deployment.apim_route_repair import APIM

NAME = "aiflux-glm-5-3-api-key"
RESOURCE_ID = APIM + "/namedValues/" + NAME
URL = "https://management.azure.com" + RESOURCE_ID + "?api-version=2024-05-01"
CLI_DIRECTORY = "C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin"


class SecretOperationBlocked(ValueError):
    """Sanitized operational error; no upstream response retained."""


def metadata(document):
    properties = document.get("properties", {})
    return {
        "resource_id": document.get("id"),
        "display_name": properties.get("displayName"),
        "secret": properties.get("secret") is True,
        "key_vault": properties.get("keyVault") is not None,
        "checked_at": datetime.now(UTC).isoformat(),
    }


def internal_ready(evidence):
    return (isinstance(evidence, dict)
            and isinstance(evidence.get("resource_id"), str)
            and evidence.get("resource_id", "").lower() == RESOURCE_ID.lower()
            and evidence.get("display_name") == NAME
            and evidence.get("secret") is True and evidence.get("key_vault") is False)


class ArmSecretStore:
    def __enter__(self):
        logging.disable(logging.CRITICAL)
        os.environ["PATH"] = CLI_DIRECTORY + os.pathsep + os.environ.get("PATH", "")
        self.credential = AzureCliCredential(process_timeout=60)
        self.session = requests.Session()
        return self

    def __exit__(self, *_):
        self.session.close()
        self.credential.close()

    def _request(self, method, **kwargs):
        token = self.credential.get_token("https://management.azure.com/.default").token
        try:
            return self.session.request(method, URL, headers={
                "Authorization": "Bearer " + token, **kwargs.pop("headers", {})
            }, timeout=(15, 60), allow_redirects=False, **kwargs)
        finally:
            token = None

    def inspect(self):
        response = self._request("GET")  # NOT listSecrets; ordinary metadata only.
        try:
            if response.status_code == 404:
                return None, None
            if response.status_code != 200:
                raise SecretOperationBlocked("Metadata check failed; no response details logged.")
            return metadata(response.json()), response.headers.get("ETag")
        finally:
            response.close()

    def install(self, value, *, exists, etag):
        if exists and not etag:
            raise SecretOperationBlocked("Rotation requires a metadata concurrency tag.")
        response = self._request("PUT", headers={
            "If-Match": etag if exists else "*",
        } if exists else {"If-None-Match": "*"}, json={"properties": {
            "displayName": NAME, "secret": True, "value": value,
            "tags": ["aiflux", "external-glm", "out-of-band-secret"],
        }})
        try:
            if response.status_code not in (200, 201):
                raise SecretOperationBlocked("Secret write not confirmed; inspect metadata before retrying.")
        finally:
            # Never parse or log the PUT response, which may contain secret data.
            response.close()