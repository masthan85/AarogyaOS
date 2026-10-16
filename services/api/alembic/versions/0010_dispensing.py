"""pharmacist records of dispensing signed prescriptions

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dispensings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("prescription_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("dispensed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status in ('DISPENSED','PARTIALLY_DISPENSED','NOT_DISPENSED')", name="ck_dispensing"
        ),
    )
    for col in ("organisation_id", "prescription_id", "patient_id"):
        op.create_index(op.f(f"ix_dispensings_{col}"), "dispensings", [col])
    policy = (
        "organisation_id = nullif(current_setting('app.org_id', true), '')::uuid "
        "OR current_setting('app.bypass', true) = 'on'"
    )
    op.execute("ALTER TABLE dispensings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dispensings FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON dispensings USING ({policy}) WITH CHECK ({policy})"
    )
    op.execute(
        """
        CREATE FUNCTION guard_dispensing() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'dispensing records are append-only';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER dispensings_guard BEFORE UPDATE OR DELETE ON dispensings "
        "FOR EACH ROW EXECUTE FUNCTION guard_dispensing()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS dispensings_guard ON dispensings")
    op.execute("DROP FUNCTION IF EXISTS guard_dispensing()")
    op.drop_table("dispensings")
