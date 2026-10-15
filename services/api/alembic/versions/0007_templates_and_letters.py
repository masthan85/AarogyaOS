"""organisation note templates; referral letters on the summaries table

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("specialty", sa.String(length=80), nullable=True),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_note_templates_organisation_id"), "note_templates", ["organisation_id"]
    )
    policy = (
        "organisation_id = nullif(current_setting('app.org_id', true), '')::uuid "
        "OR current_setting('app.bypass', true) = 'on'"
    )
    op.execute("ALTER TABLE note_templates ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE note_templates FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON note_templates USING ({policy}) WITH CHECK ({policy})"
    )

    op.add_column(
        "patient_summaries",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="VISIT_SUMMARY"),
    )
    op.add_column("patient_summaries", sa.Column("recipient", sa.String(length=200), nullable=True))
    op.alter_column("patient_summaries", "kind", server_default=None)


def downgrade() -> None:
    op.drop_column("patient_summaries", "recipient")
    op.drop_column("patient_summaries", "kind")
    op.drop_index(op.f("ix_note_templates_organisation_id"), table_name="note_templates")
    op.drop_table("note_templates")
