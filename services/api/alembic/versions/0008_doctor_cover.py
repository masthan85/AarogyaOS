"""short-term cover between doctors for results awaiting review

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cover_arrangements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("from_user_id", sa.Uuid(), nullable=False),
        sa.Column("to_user_id", sa.Uuid(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["from_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["to_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_cover_window"),
    )
    for col in ("organisation_id", "from_user_id", "to_user_id"):
        op.create_index(op.f(f"ix_cover_arrangements_{col}"), "cover_arrangements", [col])
    policy = (
        "organisation_id = nullif(current_setting('app.org_id', true), '')::uuid "
        "OR current_setting('app.bypass', true) = 'on'"
    )
    op.execute("ALTER TABLE cover_arrangements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE cover_arrangements FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON cover_arrangements "
        f"USING ({policy}) WITH CHECK ({policy})"
    )


def downgrade() -> None:
    op.drop_table("cover_arrangements")
