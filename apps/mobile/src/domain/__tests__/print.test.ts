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
    lines: [{ description: 'Dressing & care', quantity: 2, unit_price_paise: 7500, total_paise: 15000 }],
    total_paise: 15000, paid_paise: 5000, balance_paise: 10000,
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
});
