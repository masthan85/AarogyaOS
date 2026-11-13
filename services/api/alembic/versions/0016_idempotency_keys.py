"""idempotency keys for repeated money requests

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

POLICY = (
    "organisation_id = nullif(current_setting('app.org_id', true), '')::uuid "
    "OR current_setting('app.bypass', true) = 'on'"
)


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organisation_id", "user_id", "scope", "key", name="uq_idempotency_key"
        ),
    )
    op.create_index("ix_idempotency_keys_organisation_id", "idempotency_keys", ["organisation_id"])
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])
    op.execute("ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE idempotency_keys FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON idempotency_keys USING ({POLICY}) WITH CHECK ({POLICY})"
    )


def downgrade() -> None:
    # Reversible: the table holds no record of its own, only protection against repeats.
    op.drop_table("idempotency_keys")
