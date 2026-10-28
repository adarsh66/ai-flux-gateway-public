"""Read-only filtered APIM secret readiness; never fetch or print values."""
import json
import logging

from scripts.deployment.glm_apim_secret import ArmSecretStore, internal_ready


def main():
    logging.disable(logging.CRITICAL)
    try:
        with ArmSecretStore() as store:
            evidence, _ = store.inspect()
        print(json.dumps({"ready": internal_ready(evidence), "metadata": evidence}))
        return 0 if internal_ready(evidence) else 2
    except (Exception, KeyboardInterrupt):
        print("Metadata check blocked; no response or exception details logged.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())