"""Terminal admin archival; successor of budget head, never paused Feature2.

Apply only explicit 0007_admin_archival after separate rollout approval.
No rows are archived and no historical or financial records are removed.
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_admin_archival"
down_revision = "0006_monthly_advisory_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 historically imports live Base. Existing budget-head databases have
    # none of these columns; fresh test/bootstrap databases may already have
    # them. Do not lose tombstones or duplicate columns in either case.
    def add(table, column):
        if column.name not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}:
            op.add_column(table, column)

    for table in ("organizations", "members", "local_users", "team_subscriptions"):
        add(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        add(table, sa.Column("deleted_by", sa.String(36), nullable=True))
        add(table, sa.Column("deletion_reason", sa.String(500), nullable=True))
    add("team_subscriptions", sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True))
    add("team_subscriptions", sa.Column("deletion_status", sa.String(16), nullable=True))
    add("team_subscriptions", sa.Column("apim_pending_operation", sa.String(2048), nullable=True))
    add("audit_events", sa.Column("reason", sa.String(500), nullable=True))


def downgrade() -> None:
    # Dropping tombstones would permit identity resurrection. Deliberately fail
    # closed rather than provide a destructive downgrade, even on an empty DB.
    raise RuntimeError("Admin archival is irreversible; retain tombstones and audit metadata")