"""Merge the formerly duplicate 0003 branches and add isolated external prices.

Keep stable-teams' deployed 0003 identity. Give portal-users its own identity so
both upgrades run before this merge; its existing upgrade is idempotent for
databases already stamped 0003 after either historical branch.
No prices are seeded: initialize_external_baseline is an explicit operator action.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0004_external_pricing"
down_revision = ("0003", "0003_portal_users")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical portal-users deployments also used the stamp "0003". Alembic
    # then assumes stable-teams ran, so repair that branch explicitly. Its
    # upgrade is idempotent, including deterministic legacy team backfills.
    spec = spec_from_file_location("_external_stable_teams", Path(__file__).with_name("0003_stable_teams.py"))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module.upgrade()
    # 0001 historically creates live Base metadata. Support both that path and
    # existing databases without importing future application table definitions.
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("external_price_cards"):
        op.create_table(
            "external_price_cards",
            sa.Column("owner", sa.String(40), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.UniqueConstraint("organization_id"),
            sa.CheckConstraint("version >= 1"),
            sa.CheckConstraint(
                ((sa.column("owner") == "default") & sa.column("organization_id").is_(None)) |
                (sa.column("organization_id").is_not(None) &
                 (sa.column("owner") == sa.literal("org:") + sa.column("organization_id", sa.String(36)))),
                name="ck_external_price_owner",
            ),
        )
    if not sa.inspect(bind).has_table("external_price_card_revisions"):
        op.create_table(
            "external_price_card_revisions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner", sa.String(40), sa.ForeignKey("external_price_cards.owner"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("delta", sa.Text(), nullable=False),
            sa.Column("reason", sa.String(500), nullable=False),
            sa.Column("object_id", sa.String(36), nullable=False),
            sa.UniqueConstraint("owner", "version"),
            sa.CheckConstraint("version >= 1"),
        )
        op.create_index("ix_external_price_card_revisions_owner", "external_price_card_revisions", ["owner"])


def downgrade() -> None:
    op.drop_table("external_price_card_revisions")
    op.drop_table("external_price_cards")