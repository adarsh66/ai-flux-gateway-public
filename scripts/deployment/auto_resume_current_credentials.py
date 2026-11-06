"""Private stdout pipe only. One normal installed Profile acquisition, no refresh loop."""
import json
import logging
import sys


def main():
    logging.disable(logging.CRITICAL)
    from azure.cli.core import get_default_cli
    from azure.cli.core._profile import Profile
    subscription, tenant, audience = sys.argv[1:]
    if audience not in ('https://management.azure.com/', 'https://storage.azure.com/'):
        raise ValueError('audience')
    raw, actual_sub, actual_tenant = Profile(cli_ctx=get_default_cli()).get_raw_token(
        subscription=subscription, scopes=[audience+'/.default'])
    if actual_sub != subscription or actual_tenant != tenant:
        raise ValueError('context')
    sys.stdout.write(json.dumps({'access_token': raw[1]}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('{"error":"credential_acquisition_failed_no_retry"}')
        raise SystemExit(2)