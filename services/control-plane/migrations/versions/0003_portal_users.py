"""SQL portal accounts and enforced organization ownership.

0001 historically used live metadata, so both missing and legacy tables are supported.
Legacy orphan accounts are quarantined, not granted access to an arbitrary tenant.
"""

from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("portal_users"):
        op.create_table(
            "portal_users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("username", sa.String(80), nullable=False),
            sa.Column("password_hash", sa.String(128), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("organization_id", sa.String(36), nullable=False),
            sa.Column("organization_name", sa.String(100), nullable=False),
            sa.Column("tenant_id", sa.String(36), nullable=False),
            sa.Column("object_id", sa.String(36), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_portal_users_org"),
            sa.CheckConstraint("role IN ('customer', 'ids_admin')", name="ck_portal_users_role"),
            sa.UniqueConstraint("username", name="uq_portal_users_username"),
        )
        op.create_index("ix_portal_users_username", "portal_users", ["username"], unique=True)
        return
    if any(fk["constrained_columns"] == ["organization_id"] for fk in inspector.get_foreign_keys("portal_users")):
        return

    metadata = sa.MetaData()
    users = sa.Table("portal_users", metadata, autoload_with=bind)
    orgs = sa.Table("organizations", metadata, autoload_with=bind)
    orphaned = bind.execute(
        sa.select(users.c.id).where(~sa.exists().where(orgs.c.id == users.c.organization_id))
    ).scalars().all()
    for user_id in orphaned:
        org_id = str(uuid5(NAMESPACE_URL, "aiflux:quarantine:org:" + user_id))
        tenant_id = str(uuid5(NAMESPACE_URL, "aiflux:quarantine:tenant:" + user_id))
        name = "Disabled legacy portal account"
        bind.execute(orgs.insert().values(id=org_id, name=name, tenant_id=tenant_id, enabled=False))
        bind.execute(users.update().where(users.c.id == user_id).values(
            organization_id=org_id, organization_name=name, tenant_id=tenant_id, enabled=False,
        ))
    with op.batch_alter_table("portal_users") as batch:
        batch.create_foreign_key("fk_portal_users_org", "organizations", ["organization_id"], ["id"])


def downgrade() -> None:
    op.drop_table("portal_users")