"""invoices, lines and payments, with database rules that freeze what was issued

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

POLICY = (
    "organisation_id = nullif(current_setting('app.org_id', true), '')::uuid "
    "OR current_setting('app.bypass', true) = 'on'"
)


def _tenant(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({POLICY}) WITH CHECK ({POLICY})")


def upgrade() -> None:
    op.create_table(
        "invoice_counters",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("organisation_id"),
    )
    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("encounter_id", sa.Uuid(), nullable=True),
        sa.Column("number", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("total_paise", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("issued_by", sa.Uuid(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(length=200), nullable=True),
        sa.Column("voided_by", sa.Uuid(), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"]),
        sa.ForeignKeyConstraint(["encounter_id"], ["encounters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status in ('DRAFT','ISSUED','VOID')", name="ck_invoice_status"),
        sa.CheckConstraint("total_paise >= 0", name="ck_invoice_total"),
    )
    op.create_index(op.f("ix_invoices_organisation_id"), "invoices", ["organisation_id"])
    op.create_index(op.f("ix_invoices_patient_id"), "invoices", ["patient_id"])
    op.create_index("uq_invoices_number", "invoices", ["organisation_id", "number"], unique=True)
    op.create_index(
        "uq_invoices_one_per_encounter",
        "invoices",
        ["encounter_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'VOID' AND encounter_id IS NOT NULL"),
    )
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_paise", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("quantity >= 1", name="ck_line_quantity"),
        sa.CheckConstraint("unit_price_paise >= 0", name="ck_line_price"),
    )
    op.create_index("ix_invoice_lines_invoice", "invoice_lines", ["invoice_id", "position"])
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("reference", sa.String(length=60), nullable=True),
        sa.Column("received_by", sa.Uuid(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_paise > 0", name="ck_payment_amount"),
        sa.CheckConstraint("method in ('CASH','UPI','CARD','OTHER')", name="ck_payment_method"),
    )
    op.create_index(op.f("ix_payments_organisation_id"), "payments", ["organisation_id"])
    op.create_index(op.f("ix_payments_invoice_id"), "payments", ["invoice_id"])
    for table in ("invoice_counters", "invoices", "invoice_lines", "payments"):
        _tenant(table)

    # An issued invoice is frozen. A draft can change freely; an issued one can only become void,
    # with nothing else altered; a void one never changes. Only drafts can be deleted.
    op.execute(
        """
        CREATE FUNCTION guard_invoice() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.status <> 'DRAFT' THEN
              RAISE EXCEPTION 'an issued invoice cannot be deleted';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.status = 'DRAFT' THEN
            RETURN NEW;
          END IF;
          IF OLD.status = 'ISSUED' AND NEW.status = 'VOID'
             AND NEW.number IS NOT DISTINCT FROM OLD.number
             AND NEW.total_paise = OLD.total_paise
             AND NEW.patient_id = OLD.patient_id
             AND NEW.encounter_id IS NOT DISTINCT FROM OLD.encounter_id
             AND NEW.issued_at IS NOT DISTINCT FROM OLD.issued_at THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'an issued invoice is frozen: it can only be voided';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER invoices_guard BEFORE UPDATE OR DELETE ON invoices "
        "FOR EACH ROW EXECUTE FUNCTION guard_invoice()"
    )
    op.execute(
        """
        CREATE FUNCTION guard_invoice_line() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE inv_status text;
        BEGIN
          SELECT status INTO inv_status FROM invoices
            WHERE id = COALESCE(NEW.invoice_id, OLD.invoice_id);
          IF inv_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION 'the charges on an issued invoice cannot be changed';
          END IF;
          RETURN COALESCE(NEW, OLD);
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER invoice_lines_guard BEFORE INSERT OR UPDATE OR DELETE ON invoice_lines "
        "FOR EACH ROW EXECUTE FUNCTION guard_invoice_line()"
    )
    op.execute(
        """
        CREATE FUNCTION guard_payment() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE inv_status text;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION 'payments are append-only';
          END IF;
          SELECT status INTO inv_status FROM invoices WHERE id = NEW.invoice_id;
          IF inv_status IS DISTINCT FROM 'ISSUED' THEN
            RAISE EXCEPTION 'payments can only be recorded on an issued invoice';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER payments_guard BEFORE INSERT OR UPDATE OR DELETE ON payments "
        "FOR EACH ROW EXECUTE FUNCTION guard_payment()"
    )


def downgrade() -> None:
    for trigger, table in (
        ("payments_guard", "payments"),
        ("invoice_lines_guard", "invoice_lines"),
        ("invoices_guard", "invoices"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for fn in ("guard_payment", "guard_invoice_line", "guard_invoice"):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}()")
    for table in ("payments", "invoice_lines", "invoices", "invoice_counters"):
        op.drop_table(table)
