"""Enforce team tenant consistency and honor in-app preferences."""

import sqlalchemy as sa
from alembic import op

revision: str = "af0002"
down_revision: str | None = "af0001"
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_af_teams_id", "af_teams", ["id", "organization_id"])
    op.create_foreign_key(
        "fk_af_memberships_team_tenant",
        "af_memberships",
        "af_teams",
        ["team_id", "organization_id"],
        ["id", "organization_id"],
    )
    op.add_column(
        "af_notifications",
        sa.Column("visible_in_app", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("af_notifications", "visible_in_app", server_default=None)


def downgrade() -> None:
    op.drop_column("af_notifications", "visible_in_app")
    op.drop_constraint("fk_af_memberships_team_tenant", "af_memberships", type_="foreignkey")
    op.drop_constraint("uq_af_teams_id", "af_teams", type_="unique")
