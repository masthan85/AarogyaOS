"""tamper-evident seal on signed prescriptions; legal holds on patients

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

POLICY = (
    "organisation_id = nullif(current_setting('app.org_id', true), '')::uuid "
    "OR current_setting('app.bypass', true) = 'on'"
)


def upgrade() -> None:
    op.add_column("prescriptions", sa.Column("seal", sa.String(length=64), nullable=True))
    op.create_table(
        "legal_holds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("placed_by", sa.Uuid(), nullable=False),
        sa.Column(
            "placed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("released_by", sa.Uuid(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_holds_patient", "legal_holds", ["patient_id", "released_at"])
    op.execute("ALTER TABLE legal_holds ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE legal_holds FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON legal_holds USING ({POLICY}) WITH CHECK ({POLICY})"
    )
    # A hold is a record: it can be released once, with a reason, and never edited or deleted.
    op.execute(
        """
        CREATE FUNCTION guard_legal_hold() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'legal holds cannot be deleted';
          END IF;
          IF OLD.released_at IS NOT NULL
             OR NEW.patient_id <> OLD.patient_id OR NEW.reason <> OLD.reason
             OR NEW.placed_by <> OLD.placed_by OR NEW.placed_at <> OLD.placed_at
             OR NEW.released_at IS NULL OR NEW.released_by IS NULL THEN
            RAISE EXCEPTION 'a legal hold can only be released, once';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER legal_holds_guard BEFORE UPDATE OR DELETE ON legal_holds "
        "FOR EACH ROW EXECUTE FUNCTION guard_legal_hold()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS legal_holds_guard ON legal_holds")
    op.execute("DROP FUNCTION IF EXISTS guard_legal_hold()")
    op.drop_table("legal_holds")
    op.drop_column("prescriptions", "seal")
