"""Add entitlement-only tables after the verified external-pricing merge.

No historical head repair, financial updates, bootstrap or legacy import here.
Reviewed legacy conversion is an explicit separately executed operator action.
Runtime SQL grants must be supplied/verified by the deployment operator.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_org_model_access"
down_revision = "0004_external_pricing"
branch_labels = None
depends_on = None


def upgrade():
    # Frozen migration: never import mutable current application metadata.
    op.create_table("organization_model_access",
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False), sa.CheckConstraint("version >= 1"))
    op.create_table("organization_model_access_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organization_model_access.organization_id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("denied_models_json", sa.Text(), nullable=False),
        sa.Column("auto_enabled", sa.Boolean(), nullable=False),
        sa.Column("object_id", sa.String(36), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "version"), sa.CheckConstraint("version >= 1"))
    op.create_table("model_access_publication",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("applied_generation", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.String(200)), sa.Column("applied_json", sa.Text()),
        sa.Column("attempted_hash", sa.String(64)), sa.Column("predecessor_hash", sa.String(64)),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("state IN ('pending', 'applied', 'error')"))


def downgrade():
    raise RuntimeError("Entitlement audit history is retained; reviewed forward repair required")