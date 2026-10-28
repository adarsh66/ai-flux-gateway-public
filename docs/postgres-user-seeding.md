# One-time PostgreSQL account seeding

## Status

**Live seeding succeeded according to user-supplied Cloud Shell output:** final
JSON reports `database_step=seed_users`, `committed=true`, admin@tokenx-ids.com
(`ids_admin`) and developer@caldova.com (`customer`). `jwt_changes=false` and
`runtime_deployed=false`. The script verified 104 reviewed files and passed its
Entra/session/schema and single-IP firewall guards. Do not repeat seeding.

Locally tested: **63 focused tests pass** (16 seeder tests plus
47 bootstrap/credential regression tests). Instructions below are retained as
execution history, not a request to run the operation again.
Schema and runtime-principal bootstrap have already succeeded; do not repeat them.
JWT configuration and application rollout remain separate, deferred work.

This operation inserts two accounts, their required organizations and memberships
in one PostgreSQL transaction. It never overwrites existing users, resets passwords,
promotes conflicting members, creates demo usage/budgets/subscriptions, changes
Azure configuration, or creates schema/roles. Existing matching enabled
organizations/memberships may be reused; conflicting ones fail closed.

## Upload to the existing Bash Cloud Shell

Use Cloud Shell's upload control to upload the current
[seeder](../infra/sql/seed-postgres-users.py) and, if necessary, the reviewed
[bootstrap companion](../infra/sql/bootstrap-postgres.py).
Place both together under `$HOME/aiflux-pg-bootstrap`. Keep the previously uploaded
reviewed release, its manifest and extracted context in place. Do not upload
passwords, use chat to transmit them, or pass them in commands/environment variables.

The existing Cloud Shell virtual environment must retain the dependencies installed
for the successful bootstrap. Neither Key Vault access nor a JWT secret is needed.
The signed-in CLI user must still be the approved Entra PostgreSQL administrator.

Run in **Bash Cloud Shell**, not PowerShell or the local workstation:

```bash
cd "$HOME/aiflux-pg-bootstrap"
sha256sum seed-postgres-users.py bootstrap-postgres.py
```

Expected SHA256 values:

- Seeder: `e119d8a4a9b8ff73545f71e10487a368169bfca447135feeb9fc2221769748b1`
- Bootstrap companion: `91cd0d5414f5a7cdc2253b25fe599c0982a84b722b0487091ada3d139a8258bf`

The seeder also verifies the companion checksum itself and verifies all 104
reviewed release files before importing models/hashing functions.

## Review account metadata, then execute

The command below explicitly selects:

| Email | Role | Organization |
| --- | --- | --- |
| admin@tokenx-ids.com | ids_admin | Singtel IDS |
| developer@caldova.com | customer | Caldova |

Change the two email options/customer organization **before execution** if different
accounts are intended. The home organization uses the approved Entra tenant;
the customer uses the application's existing synthetic tenant convention.

Locate the previously uploaded manifest below the bootstrap folder. If multiple
copies exist, select the intended reviewed release directory explicitly instead.

```bash
mapfile -t manifests < <(find "$HOME/aiflux-pg-bootstrap" -type f -name source-manifest.json)
if [ "${#manifests[@]}" -ne 1 ]; then
  printf '%s\n' 'Expected exactly one release manifest; select the reviewed release directory explicitly.'
else
  release_dir="$(dirname "${manifests[0]}")"
  "$HOME/aiflux-pg-bootstrap/.venv/bin/python" seed-postgres-users.py \
    --release-dir "$release_dir" \
    --subscription aa28274d-fea0-46d4-b9c8-30f3ef0a0e52 \
    --tenant beb276ac-6e9f-498e-8e31-019ee666decd \
    --resource-group IDS-TOKEN-EXCHANGE-POC \
    --server poc-ids-token-ex-pg \
    --database turnstile \
    --admin-object-id dd928302-055b-4516-9b8e-b06ae823057b \
    --approved-public-ip 135.171.36.90 \
    --admin-email admin@tokenx-ids.com \
    --customer-email developer@caldova.com \
    --customer-org Caldova \
    --execute
fi
```

The IP is the **previously approved** Cloud Shell address, not an assumption about
the current session. The script re-reads Azure configuration and refuses database
writes unless PostgreSQL public access is disabled (reachable private route) or
the public firewall contains exactly that single address. A changed Cloud Shell IP
requires separate approval/network reconciliation; do not widen access or add
`0.0.0.0`. The script makes no firewall changes.

After network, Entra identity/mapping, database session and schema `0003` checks,
enter each password twice at the hidden prompts. Use different passwords,
16–1024 characters long with at least eight distinct characters; save them in your
own approved password manager. No default password is supplied. Piped input and
terminals that cannot suppress echo are rejected.

Only salted PBKDF2-SHA256 hashes using the reviewed application's exact implementation
are inserted into `local_users`. Passwords necessarily exist briefly in Python
memory; Python cannot guarantee memory zeroization. No password or hash is printed
or written into local credential files. The process exits after the one-time task.

## Expected result and follow-up

The final JSON must report `database_step: seed_users`, `committed: true` and the
two selected emails/roles. Share only that final nonsensitive JSON for confirmation.
A duplicate-account failure means nothing was reset: do not delete users or change
the script to force an overwrite. A connection interruption around commit requires
a read-only database check before retrying; a missing acknowledgment is not proof
the commit failed.

Success proves account insertion, not portal login. JWT signing configuration,
runtime configuration changes/rebuild, deployment and end-to-end login tests remain
pending. Temporary PostgreSQL public access must subsequently be closed through
the approved Terraform containment workflow; this seeder does not perform cleanup.
The existing backend-storage access blocker must not be bypassed with broad network
rules or new permissions.