"""procedures, immunisations and referrals as provenance-carrying clinical facts

Revision ID: 0012
Revises: 0011
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

POLICY = (
    "organisation_id = nullif(current_setting('app.org_id', true), '')::uuid "
    "OR current_setting('app.bypass', true) = 'on'"
)


def _fact_columns(
    table: str,
) -> list[sa.Column[Any] | sa.ForeignKeyConstraint | sa.PrimaryKeyConstraint]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("encounter_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("verification_state", sa.String(length=20), nullable=False),
        sa.Column("recorded_by", sa.Uuid(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=300), nullable=True),
        sa.Column("evidence_segment_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"]),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
    ]


def upgrade() -> None:
    op.create_table(
        "procedure_records",
        sa.Column("display", sa.String(length=300), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=True),
        sa.Column("code_system", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("performed_on", sa.Date(), nullable=False),
        sa.Column("body_site", sa.String(length=120), nullable=True),
        sa.Column("outcome", sa.String(length=500), nullable=True),
        sa.Column("complications", sa.String(length=500), nullable=True),
        *_fact_columns("procedure_records"),
    )
    op.create_table(
        "immunisations",
        sa.Column("vaccine", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=True),
        sa.Column("code_system", sa.String(length=40), nullable=True),
        sa.Column("dose_number", sa.Integer(), nullable=True),
        sa.Column("given_on", sa.Date(), nullable=False),
        sa.Column("given_here", sa.Boolean(), nullable=False),
        sa.Column("batch_number", sa.String(length=60), nullable=True),
        sa.Column("site", sa.String(length=60), nullable=True),
        sa.Column("next_due_on", sa.Date(), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        *_fact_columns("immunisations"),
    )
    op.create_table(
        "referrals",
        sa.Column("to_specialty", sa.String(length=120), nullable=False),
        sa.Column("to_name", sa.String(length=200), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("urgency", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("outcome_note", sa.String(length=500), nullable=True),
        *_fact_columns("referrals"),
    )
    for table, index in (
        ("procedure_records", "ix_procedure_records_patient"),
        ("immunisations", "ix_immunisations_patient"),
        ("referrals", "ix_referrals_patient"),
    ):
        op.create_index(index, table, ["patient_id", "is_current"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({POLICY}) WITH CHECK ({POLICY})"
        )
        op.execute(
            f"CREATE TRIGGER {table}_guard BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION guard_clinical_fact()"
        )


def downgrade() -> None:
    for table in ("referrals", "immunisations", "procedure_records"):
        op.drop_table(table)
