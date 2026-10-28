"""Private-job entrypoint with non-secret SQLSTATE/numeric-code diagnostics only.

Never print exception
strings, SQL statements, parameter values, tokens or raw driver messages.
"""

from __future__ import annotations

import json
import logging
import sys
import warnings

if __package__:
    from . import private_sql_job as job
else:
    import private_sql_job as job


def main() -> int:
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")
    checks: list[str] = []
    try:
        parser = job.SafeParser(allow_abbrev=False)
        parser.add_argument("mode", choices=("probe", "migrate"))
        for name in ("sql-host", "sql-database", "tenant-id", "operator-object-id",
                     "api-client-id", "private-cidr"):
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--seed", action="store_true")
        parser.add_argument("--verify-api-mi", action="store_true")
        job.run_job(job.JobConfig(**vars(parser.parse_args())), checks)
    except Exception as error:
        code = "job_failed"
        if isinstance(error, job.JobError) and len(error.args) == 1 and error.args[0] in job.ERROR_CODES:
            code = error.args[0]
        state, numbers = job.driver_codes(error)
        stage = getattr(error, "aiflux_sql_stage", None)
        stage = stage if type(stage) is str and stage in job.SQL_STAGES else None
        print(json.dumps({"status": "failed", "code": code, "checks": checks}))
        print(json.dumps({"diagnostic": "sql_driver", "sqlstate": state,
                  "native_codes": numbers, "stage": stage, "exception_type": type(error).__name__
                          if type(error).__name__ in {"ProgrammingError", "OperationalError",
                                                     "IntegrityError", "JobError", "DBAPIError"}
                          else "other"}))
        return 1
    print(json.dumps({"status": "ok", "checks": checks}))
    return 0


if __name__ == "__main__":
    sys.exit(main())