"""Masked out-of-band rotated credential entry. Never run via a captured prompt.

Only writes the fixed APIM encrypted secret named value out-of-band. No vault,
identity, RBAC, network, Terraform or public metadata mutations.
"""
import getpass
import logging
import sys
import warnings


def main() -> int:
    if len(sys.argv) != 1:
        print("Blocked: command-line arguments are not accepted; use masked interactive entry only.")
        return 1
    if not sys.stdin.isatty():
        print("Blocked: enter the rotated replacement directly in an interactive terminal.")
        return 1
    logging.disable(logging.CRITICAL)
    try:
        from scripts.deployment.glm_apim_secret import ArmSecretStore, internal_ready

        with ArmSecretStore() as store:
            prior, etag = store.inspect()
            if prior is not None and not internal_ready(prior):
                print("Blocked: existing named value is not the reviewed internal secret type.")
                return 1
            # A missing protected console must fail, never echo stdin.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                value = getpass.getpass("Rotated GLM API key (masked; never paste into chat): ")
            try:
                if not value or len(value) > 4096 or any(c.isspace() for c in value):
                    print("Blocked: invalid credential format; no value was written.")
                    return 1
                store.install(value, exists=prior is not None, etag=etag)
            finally:
                value = ""  # Python cannot promise memory zeroization.
            current, _ = store.inspect()
            if not internal_ready(current):
                print("Write attempted but metadata readiness not confirmed; GLM remains disabled.")
                return 1
        print("APIM encrypted secret stored; metadata verified. GLM still requires guarded deployment and metered inference.")
        return 0
    except (Exception, KeyboardInterrupt):
        # SDK exception text/tracebacks may contain sensitive HTTP details.
        print("Secret installation blocked or cancelled. No exception detail was logged; verify approved access.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())