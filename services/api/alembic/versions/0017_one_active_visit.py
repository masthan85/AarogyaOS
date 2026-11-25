"""one active visit per patient; idempotency keys remember what they created

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

ACTIVE = "status IN ('WAITING', 'CHECKED_IN', 'IN_CONSULTATION')"


def upgrade() -> None:
    op.add_column("idempotency_keys", sa.Column("resource_id", sa.Uuid(), nullable=True))
    # The service already refuses a second check-in for a patient who is waiting or being seen;
    # this makes the rule hold when two requests arrive together. If it fails to create, a patient
    # already has two active visits: close one by hand before upgrading.
    op.create_index(
        "uq_appointments_one_active_visit",
        "appointments",
        ["patient_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
    )


def downgrade() -> None:
    op.drop_index("uq_appointments_one_active_visit", table_name="appointments")
    op.drop_column("idempotency_keys", "resource_id")
