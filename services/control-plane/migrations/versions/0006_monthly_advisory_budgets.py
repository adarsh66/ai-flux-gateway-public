"""Independent monthly-advisory sibling of PAUSED 0005 model access.

On a database already at 0004_external_pricing, apply ONLY the explicit target
0006_monthly_advisory_budgets (or monthly_advisory_budgets@head). NEVER `heads`:
that would also run paused Feature2. No runtime DDL or automatic initialization.
Historical 0001 imports live Base metadata: fresh empty-database upgrades are
NOT Feature2-isolated until that older bootstrap is separately repaired.

Downgrade removes policy/revision schema but retains remediation audit and the
OFF default. It intentionally never restores captured true flags. Re-upgrade
preserves the first remediation receipt. No allocations or financial balances
are copied/seeded and no allowance/usage/history rows are reset or deleted.
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_monthly_advisory_budgets"
down_revision = "0004_external_pricing"
branch_labels = ("monthly_advisory_budgets",)
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("organization_monthly_budget_policies"):
        op.create_table("organization_monthly_budget_policies",
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), primary_key=True),
            sa.Column("version", sa.Integer(), nullable=False), sa.CheckConstraint("version >= 1"))
    if not sa.inspect(bind).has_table("organization_monthly_budget_revisions"):
        op.create_table("organization_monthly_budget_revisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organization_monthly_budget_policies.organization_id"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("allocated_usd", sa.Numeric(20, 4), nullable=False),
            sa.Column("advisory_threshold_pct", sa.Integer(), nullable=False, server_default="80"),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column("changed_by", sa.String(36), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "version"), sa.CheckConstraint("version >= 1"),
            sa.CheckConstraint("allocated_usd > 0 AND allocated_usd <= 1000000000"),
            sa.CheckConstraint("advisory_threshold_pct >= 1 AND advisory_threshold_pct <= 100"))
        op.create_index("ix_monthly_budget_revision_org_time", "organization_monthly_budget_revisions", ["organization_id", "changed_at"])
    if not sa.inspect(bind).has_table("budget_hard_stop_remediations"):
        op.create_table("budget_hard_stop_remediations",
            sa.Column("budget_id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), nullable=False),
            sa.Column("previous_hard_stop_enabled", sa.Boolean(), nullable=False),
            sa.Column("remediated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sa.String(500), nullable=False))
    budgets = sa.table("credit_budgets", sa.column("id"), sa.column("organization_id"),
                       sa.column("hard_stop_enabled", sa.Boolean()))
    receipts = sa.table("budget_hard_stop_remediations", sa.column("budget_id"), sa.column("organization_id"),
                        sa.column("previous_hard_stop_enabled", sa.Boolean()),
                        sa.column("remediated_at", sa.DateTime(timezone=True)), sa.column("reason"))
    op.execute(receipts.insert().from_select(
        ["budget_id", "organization_id", "previous_hard_stop_enabled", "remediated_at", "reason"],
        sa.select(budgets.c.id, budgets.c.organization_id, budgets.c.hard_stop_enabled,
                  sa.func.current_timestamp(), sa.literal("0006 monthly advisory: disable legacy budget hard stop"))
          .where(budgets.c.hard_stop_enabled.is_(True),
                 ~sa.exists(sa.select(1).where(receipts.c.budget_id == budgets.c.id)))))
    op.execute(budgets.update().where(budgets.c.hard_stop_enabled.is_(True)).values(hard_stop_enabled=False))
    with op.batch_alter_table("credit_budgets") as batch:
        batch.alter_column("hard_stop_enabled", existing_type=sa.Boolean(), existing_nullable=False,
                           server_default=sa.false())


def downgrade() -> None:
    # Retain the OFF default and audit, including original true values.
    # No safe rollback may silently restore blocking behavior.
    op.drop_table("organization_monthly_budget_revisions")
    op.drop_table("organization_monthly_budget_policies")