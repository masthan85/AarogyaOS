"""append-only corrections to transcript lines

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcript_corrections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("segment_id", sa.Uuid(), nullable=False),
        sa.Column("interaction_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("corrected_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["segment_id"], ["transcript_segments.id"]),
        sa.ForeignKeyConstraint(["interaction_id"], ["clinical_interactions.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("organisation_id", "segment_id", "interaction_id"):
        op.create_index(op.f(f"ix_transcript_corrections_{col}"), "transcript_corrections", [col])
    policy = (
        "organisation_id = nullif(current_setting('app.org_id', true), '')::uuid "
        "OR current_setting('app.bypass', true) = 'on'"
    )
    op.execute("ALTER TABLE transcript_corrections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE transcript_corrections FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON transcript_corrections "
        f"USING ({policy}) WITH CHECK ({policy})"
    )
    # A correction is a record of what a person did: it is added, never changed or removed.
    op.execute(
        """
        CREATE FUNCTION guard_transcript_correction() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'transcript corrections are append-only';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER transcript_corrections_guard BEFORE UPDATE OR DELETE ON "
        "transcript_corrections FOR EACH ROW EXECUTE FUNCTION guard_transcript_correction()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS transcript_corrections_guard ON transcript_corrections")
    op.execute("DROP FUNCTION IF EXISTS guard_transcript_correction()")
    op.drop_table("transcript_corrections")
