"""Explicit operator migration; never invoked by usage, catalog reads or API startup."""

import argparse
from uuid import UUID

from sqlalchemy.orm import Session

from aiflux.auth import Principal
from aiflux.config import get_settings
from aiflux.db import engine_for
from aiflux.external_pricing import initialize_external_baseline


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--init-baseline", action="store_true", required=True,
                        help="Freeze internal pricing into the independent external baseline")
    parser.add_argument("--actor-object-id", type=UUID, required=True,
                        help="Administrator object ID retained in the migration audit")
    args = parser.parse_args(argv)
    settings = get_settings()
    if not settings.database_url:
        parser.error("AIFLUX_DATABASE_URL is required")
    # Trusted operator command, like price_bootstrap; not a public role grant.
    principal = Principal("", "Operator", "", str(args.actor_object_id), "ids_admin")
    with Session(engine_for(settings.database_url)) as db:
        result = initialize_external_baseline(db, settings, principal)
    print(f"External baseline version={result.version} changed={result.changed}")


if __name__ == "__main__":
    main()