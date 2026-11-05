"""tax lines, price list, credit notes, refunds, day closing and insurance claims

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

POLICY = (
    "organisation_id = nullif(current_setting('app.org_id', true), '')::uuid "
    "OR current_setting('app.bypass', true) = 'on'"
)
METHODS = "('CASH','UPI','CARD','INSURER','OTHER')"


def _tenant(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({POLICY}) WITH CHECK ({POLICY})")


def _id_org() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
    ]


def _now(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _replace_method_check(methods: str) -> None:
    # The constraint may carry the naming-convention prefix, so find it by what it checks.
    op.execute(
        """
        DO $$ DECLARE c text; BEGIN
          FOR c IN SELECT conname FROM pg_constraint
                   WHERE conrelid = 'payments'::regclass AND contype = 'c'
                     AND pg_get_constraintdef(oid) ILIKE '%method%' LOOP
            EXECUTE format('ALTER TABLE payments DROP CONSTRAINT %I', c);
          END LOOP;
        END $$
        """
    )
    op.execute(
        f"ALTER TABLE payments ADD CONSTRAINT ck_payments_method CHECK (method in {methods})"
    )


def upgrade() -> None:
    op.add_column(
        "invoice_counters",
        sa.Column("last_credit_note", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "invoices", sa.Column("tax_paise", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("invoices", sa.Column("seller_gstin", sa.String(length=15), nullable=True))
    op.add_column(
        "invoice_lines", sa.Column("tax_rate_bp", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_check_constraint(
        "ck_line_tax_rate", "invoice_lines", "tax_rate_bp between 0 and 2800"
    )
    _replace_method_check(METHODS)

    op.create_table(
        "billing_settings",
        sa.Column("organisation_id", sa.Uuid(), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=True),
        sa.Column("legal_name", sa.String(length=200), nullable=True),
        _now("updated_at"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("organisation_id"),
    )
    op.create_table(
        "service_prices",
        *_id_org(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("tax_rate_bp", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _now("created_at"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("price_paise >= 0", name="ck_price_amount"),
        sa.CheckConstraint("tax_rate_bp between 0 and 2800", name="ck_price_tax"),
    )
    op.create_index("ix_service_prices_org", "service_prices", ["organisation_id", "active"])
    op.create_index(
        "uq_service_prices_name",
        "service_prices",
        ["organisation_id", sa.text("lower(name)")],
        unique=True,
    )
    op.create_table(
        "credit_notes",
        *_id_org(),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _now("created_at"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_paise > 0", name="ck_credit_amount"),
    )
    op.create_index("ix_credit_notes_invoice", "credit_notes", ["invoice_id"])
    op.create_index(
        "uq_credit_notes_number", "credit_notes", ["organisation_id", "number"], unique=True
    )
    op.create_table(
        "refunds",
        *_id_org(),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("reference", sa.String(length=60), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("refunded_by", sa.Uuid(), nullable=False),
        _now("refunded_at"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_paise > 0", name="ck_refund_amount"),
        sa.CheckConstraint(f"method in {METHODS}", name="ck_refund_method"),
    )
    op.create_index("ix_refunds_invoice", "refunds", ["invoice_id"])
    op.create_table(
        "cash_closings",
        *_id_org(),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("expected_cash_paise", sa.Integer(), nullable=False),
        sa.Column("counted_cash_paise", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("closed_by", sa.Uuid(), nullable=False),
        _now("closed_at"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("counted_cash_paise >= 0", name="ck_closing_counted"),
    )
    op.create_index(
        "uq_cash_closings_day", "cash_closings", ["organisation_id", "business_date"], unique=True
    )
    op.create_table(
        "insurance_claims",
        *_id_org(),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("insurer", sa.String(length=120), nullable=False),
        sa.Column("policy_number", sa.String(length=60), nullable=True),
        sa.Column("claim_reference", sa.String(length=60), nullable=True),
        sa.Column("claimed_paise", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("approved_paise", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("claimed_paise > 0", name="ck_claim_amount"),
        sa.CheckConstraint(
            "status in ('SUBMITTED','APPROVED','PART_APPROVED','REJECTED','SETTLED')",
            name="ck_claim_status",
        ),
    )
    op.create_index("ix_insurance_claims_invoice", "insurance_claims", ["invoice_id"])
    for table in (
        "billing_settings", "service_prices", "credit_notes", "refunds", "cash_closings",
        "insurance_claims",
    ):  # fmt: skip
        _tenant(table)

    # Credit notes, refunds and day closings are records of what happened: append-only.
    op.execute(
        """
        CREATE FUNCTION guard_billing_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE inv_status text;
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
          END IF;
          IF TG_TABLE_NAME IN ('credit_notes', 'refunds') THEN
            SELECT status INTO inv_status FROM invoices WHERE id = NEW.invoice_id;
            IF inv_status IS DISTINCT FROM 'ISSUED' THEN
              RAISE EXCEPTION 'only an issued invoice can be credited or refunded';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    for table in ("credit_notes", "refunds", "cash_closings"):
        op.execute(
            f"CREATE TRIGGER {table}_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION guard_billing_append_only()"
        )

    # The frozen set now includes the tax and the seller's GSTIN as printed.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_invoice() RETURNS trigger LANGUAGE plpgsql AS $$
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
             AND NEW.tax_paise = OLD.tax_paise
             AND NEW.seller_gstin IS NOT DISTINCT FROM OLD.seller_gstin
             AND NEW.patient_id = OLD.patient_id
             AND NEW.encounter_id IS NOT DISTINCT FROM OLD.encounter_id
             AND NEW.issued_at IS NOT DISTINCT FROM OLD.issued_at THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'an issued invoice is frozen: it can only be voided';
        END $$
        """
    )


def downgrade() -> None:
    for table in (
        "insurance_claims",
        "cash_closings",
        "refunds",
        "credit_notes",
        "service_prices",
        "billing_settings",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS guard_billing_append_only()")
    _replace_method_check("('CASH','UPI','CARD','OTHER')")
    op.drop_column("invoice_lines", "tax_rate_bp")
    op.drop_column("invoices", "seller_gstin")
    op.drop_column("invoices", "tax_paise")
    op.drop_column("invoice_counters", "last_credit_note")
