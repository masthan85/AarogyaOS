"""job runs and optional pgvector search

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_job_runs_name"), "job_runs", ["name"])

    # pgvector is optional. A DBA installs the extension (CREATE EXTENSION vector, which needs
    # privileges the application role does not have); if it is there, reference search runs in
    # the database, otherwise the application ranks in Python. Both give the same results.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
            ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_vec vector;
            UPDATE knowledge_chunks SET embedding_vec = embedding::vector;
            DROP TRIGGER IF EXISTS knowledge_chunks_guard ON knowledge_chunks;
            CREATE TRIGGER knowledge_chunks_guard BEFORE UPDATE OR DELETE ON knowledge_chunks
              FOR EACH ROW EXECUTE FUNCTION guard_columns('embedding_vec');
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.columns
                     WHERE table_name = 'knowledge_chunks' AND column_name = 'embedding_vec') THEN
            DROP TRIGGER IF EXISTS knowledge_chunks_guard ON knowledge_chunks;
            ALTER TABLE knowledge_chunks DROP COLUMN embedding_vec;
            CREATE TRIGGER knowledge_chunks_guard BEFORE UPDATE OR DELETE ON knowledge_chunks
              FOR EACH ROW EXECUTE FUNCTION guard_columns('');
          END IF;
        END $$
        """
    )
    op.drop_index(op.f("ix_job_runs_name"), table_name="job_runs")
    op.drop_table("job_runs")
