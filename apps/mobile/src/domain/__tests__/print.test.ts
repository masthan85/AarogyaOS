import type { ClinicalDocument, Invoice, Prescription } from '@/api/schemas';

import { documentHtml, escapeHtml, invoiceHtml, prescriptionHtml, type Letterhead } from '../print';

const head: Letterhead = { facility: 'Alpha <Clinic>', address: '1 Main Rd', doctor: 'Dr Rao', registration: 'KMC 123', patient: 'Lakshmi "Devi"', patientLine: '45 years, female, MRN 7' };
const rx = (o: Partial<Prescription>): Prescription => ({
  id: 'r', status: 'SIGNED', signed_at: '2026-10-15T10:00:00Z',
  items: [{ id: 'i', position: 1, medicine_name: 'Paracetamol <500>', strength: '500 mg', dose: '1 tablet', route: 'ORAL', frequency: 'twice daily', duration_days: 5, instructions: 'after food & water' }],
  ...o,
});
const doc = (o: Partial<ClinicalDocument>): ClinicalDocument => ({
  id: 'd', encounter_id: 'e', kind: 'VISIT_SUMMARY', recipient: null, version: 2, language: 'en-IN', content: 'Rest <b>well</b>.\nDrink water.',
  source_content: 'x', translation_status: 'NOT_NEEDED', status: 'APPROVED', approved_at: '2026-10-15T10:00:00Z', created_at: '2026-10-15', ...o,
});

describe('printing', () => {
  it('escapes anything that could be read as markup', () => {
    expect(escapeHtml(`<script>alert('x')</script> & "q"`)).toBe('&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt; &amp; &quot;q&quot;');
  });

  it('prints only signed prescriptions', () => {
    expect(prescriptionHtml(rx({ status: 'DRAFT' }), head)).toBeNull();
    expect(prescriptionHtml(rx({ status: 'VOIDED' }), head)).toBeNull();
    const html = prescriptionHtml(rx({}), head) as string;
    expect(html).toContain('Paracetamol &lt;500&gt;');
    expect(html).toContain('after food &amp; water');
    expect(html).toContain('Registration no. KMC 123');
    expect(html).not.toContain('<500>');
    expect(html).toContain('Lakshmi &quot;Devi&quot;');
  });

  it('prints only approved documents, with who approved them', () => {
    expect(documentHtml(doc({ status: 'DRAFT' }), head, 'Dr Rao')).toBeNull();
    const html = documentHtml(doc({}), head, 'Dr Rao') as string;
    expect(html).toContain('Rest &lt;b&gt;well&lt;/b&gt;.');
    expect(html).toContain('Approved in AarogyaOS by Dr Rao');
    expect(html).toContain('version 2');
  });

  it('says when a translation was checked by the doctor', () => {
    expect(documentHtml(doc({ translation_status: 'CLINICIAN_EDITED' }), head, 'Dr Rao')).toContain('translation checked by the doctor');
  });
});

describe('invoiceHtml', () => {
  const inv: Invoice = {
    id: 'i', number: 'INV-000007', status: 'ISSUED', patient_id: 'p', patient_name: 'Ravi <Kumar>', patient_mrn: 'P0000001', encounter_id: null,
    lines: [{ description: 'Dressing & care', quantity: 2, unit_price_paise: 7500, tax_rate_bp: 0, tax_paise: 0, total_paise: 15000 }],
    tax_paise: 0, total_paise: 15000, seller_gstin: null, credited_paise: 0, net_paise: 15000, paid_paise: 5000, refunded_paise: 0, balance_paise: 10000, refund_due_paise: 0,
    credit_notes: [], refunds: [],
    payments: [{ id: 'x', amount_paise: 5000, method: 'UPI', reference: 'R1', received_at: '2026-03-01T10:00:00Z' }],
    created_at: '2026-03-01T09:00:00Z', issued_at: '2026-03-01T09:30:00Z', void_reason: null,
  };
  it('prints only issued invoices, with amounts, balance and escaped text', () => {
    const html = invoiceHtml(inv, 'Alpha <Clinic>') ?? '';
    expect(html).toContain('INV-000007');
    expect(html).toContain('Ravi &lt;Kumar&gt;');
    expect(html).toContain('Alpha &lt;Clinic&gt;');
    expect(html).toContain('Dressing &amp; care');
    expect(html).toContain('₹150');
    expect(html).toContain('Balance due ₹100');
    expect(html).toContain('by UPI (ref. R1)');
    expect(invoiceHtml({ ...inv, balance_paise: 0 }, 'A')).toContain('Paid in full');
    expect(invoiceHtml({ ...inv, status: 'DRAFT', number: null }, 'A')).toBeNull();
    expect(invoiceHtml({ ...inv, status: 'VOID' }, 'A')).toBeNull();
  });
  it('shows tax, the seller GSTIN and any credit note or refund', () => {
    const taxed: Invoice = {
      ...inv,
      lines: [{ ...inv.lines[0], tax_rate_bp: 1800, tax_paise: 2700 }], tax_paise: 2700, total_paise: 17700, seller_gstin: '29ABCDE1234F1Z5',
      credit_notes: [{ number: 'CN-000001', amount_paise: 1000, reason: 'Rebate <ok>', created_at: '2026-03-02T00:00:00Z' }], net_paise: 16700,
      refunds: [{ amount_paise: 500, method: 'CASH', reason: 'x', reference: null, refunded_at: '2026-03-02T00:00:00Z' }],
    };
    const html = invoiceHtml(taxed, 'A') ?? '';
    expect(html).toContain('Tax invoice');
    expect(html).toContain('GSTIN 29ABCDE1234F1Z5');
    expect(html).toContain('18%');
    expect(html).toContain('CN-000001');
    expect(html).toContain('Rebate &lt;ok&gt;');
    expect(html).toContain('Net ₹167');
    expect(html).toContain('Refunded');
    expect(invoiceHtml(inv, 'A')).not.toContain('Tax invoice');
  });
});
