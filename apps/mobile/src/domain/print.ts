import type { ClinicalDocument, Invoice, Prescription } from '@/api/schemas';

import { formatRupees, METHOD_LABELS } from './billing';

/** Everything that goes into a printed page is escaped: text from patients and doctors is untrusted. */
export const escapeHtml = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

export type Letterhead = {
  facility: string;
  address?: string | null;
  doctor: string;
  registration?: string | null;
  patient: string;
  patientLine: string; // for example "45 years, female, MRN 123"
};

const STYLE = `
  body { font-family: -apple-system, Roboto, 'Noto Sans', sans-serif; margin: 28px; color: #111; font-size: 14px; }
  h1 { font-size: 20px; margin: 0 0 2px; } h2 { font-size: 16px; margin: 18px 0 6px; }
  .muted { color: #555; } .head { border-bottom: 2px solid #111; padding-bottom: 8px; margin-bottom: 12px; }
  table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #999; padding: 6px; text-align: left; vertical-align: top; }
  .body { white-space: pre-wrap; line-height: 1.5; } .foot { margin-top: 28px; font-size: 11px; color: #555; }
`;

function head(h: Letterhead, date: string): string {
  return `<div class="head"><h1>${escapeHtml(h.facility)}</h1>
    ${h.address ? `<div class="muted">${escapeHtml(h.address)}</div>` : ''}
    <div>${escapeHtml(h.doctor)}${h.registration ? ` · Registration no. ${escapeHtml(h.registration)}` : ''}</div></div>
    <div><strong>${escapeHtml(h.patient)}</strong> <span class="muted">${escapeHtml(h.patientLine)}</span></div>
    <div class="muted">Date: ${escapeHtml(date)}</div>`;
}

const page = (inner: string) => `<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"/><style>${STYLE}</style></head><body>${inner}</body></html>`;

/** Only an approved document may be printed: the page says who approved it and when. */
export function documentHtml(d: ClinicalDocument, h: Letterhead, approvedBy: string): string | null {
  if (d.status !== 'APPROVED') return null;
  const when = d.approved_at ? new Date(d.approved_at).toLocaleDateString() : '';
  return page(`${head(h, when)}<div class="body" style="margin-top:14px">${escapeHtml(d.content)}</div>
    <div class="foot">Approved in AarogyaOS by ${escapeHtml(approvedBy)}${when ? ` on ${escapeHtml(when)}` : ''} · version ${d.version}${
      d.translation_status === 'CLINICIAN_EDITED' ? ' · translation checked by the doctor' : ''
    }</div>`);
}

/** Only a signed prescription may be printed. A draft or voided one returns null. */
export function prescriptionHtml(rx: Prescription, h: Letterhead): string | null {
  if (rx.status !== 'SIGNED') return null;
  const when = rx.signed_at ? new Date(rx.signed_at).toLocaleString() : '';
  const rows = [...rx.items]
    .sort((a, b) => a.position - b.position)
    .map(
      (i) => `<tr><td>${i.position}</td><td>${escapeHtml(i.medicine_name)}${i.strength ? ` ${escapeHtml(i.strength)}` : ''}</td>
        <td>${escapeHtml(i.dose)}</td><td>${escapeHtml(i.route.toLowerCase())}</td><td>${escapeHtml(i.frequency)}</td>
        <td>${i.duration_days ? `${i.duration_days} days` : ''}</td><td>${i.instructions ? escapeHtml(i.instructions) : ''}</td></tr>`,
    )
    .join('');
  return page(`${head(h, when)}<h2>Prescription</h2>
    <table><tr><th>#</th><th>Medicine</th><th>Dose</th><th>Route</th><th>How often</th><th>For</th><th>Notes</th></tr>${rows}</table>
    <div class="foot">Signed electronically in AarogyaOS by ${escapeHtml(h.doctor)}${when ? ` on ${escapeHtml(when)}` : ''}.
    Check that this form meets the prescription rules that apply where you practise.</div>`);
}

/** Only an issued invoice may be printed. It carries charges and payments, never anything clinical. */
export function invoiceHtml(inv: Invoice, organisation: string): string | null {
  if (inv.status !== 'ISSUED' || !inv.number) return null;
  const when = inv.issued_at ? new Date(inv.issued_at).toLocaleDateString() : '';
  const taxed = inv.tax_paise > 0;
  const rows = inv.lines
    .map(
      (l, i) => `<tr><td>${i + 1}</td><td>${escapeHtml(l.description)}</td><td style="text-align:right">${l.quantity}</td>
        <td style="text-align:right">${escapeHtml(formatRupees(l.unit_price_paise))}</td>${taxed ? `<td style="text-align:right">${l.tax_rate_bp / 100}%</td><td style="text-align:right">${escapeHtml(formatRupees(l.tax_paise))}</td>` : ''}<td style="text-align:right">${escapeHtml(formatRupees(l.total_paise))}</td></tr>`,
    )
    .join('');
  const paid = inv.payments
    .map((p) => `<div>${escapeHtml(new Date(p.received_at).toLocaleDateString())}: ${escapeHtml(formatRupees(p.amount_paise))} by ${escapeHtml(METHOD_LABELS[p.method] ?? p.method)}${p.reference ? ` (ref. ${escapeHtml(p.reference)})` : ''}</div>`)
    .join('');
  const credits = inv.credit_notes
    .map((c) => `<div>Credit note ${escapeHtml(c.number)}: -${escapeHtml(formatRupees(c.amount_paise))} (${escapeHtml(c.reason)})</div>`)
    .join('');
  const refunds = inv.refunds
    .map((r) => `<div>Refunded ${escapeHtml(new Date(r.refunded_at).toLocaleDateString())}: ${escapeHtml(formatRupees(r.amount_paise))} by ${escapeHtml(METHOD_LABELS[r.method] ?? r.method)}</div>`)
    .join('');
  return page(`<div class="head"><h1>${escapeHtml(organisation)}</h1><div>${taxed && inv.seller_gstin ? 'Tax invoice' : 'Invoice'} ${escapeHtml(inv.number)}${when ? ` · ${escapeHtml(when)}` : ''}</div>${inv.seller_gstin ? `<div class="muted">GSTIN ${escapeHtml(inv.seller_gstin)}</div>` : ''}</div>
    <div><strong>${escapeHtml(inv.patient_name)}</strong> <span class="muted">MRN ${escapeHtml(inv.patient_mrn)}</span></div>
    <table style="margin-top:12px"><tr><th>#</th><th>Charge</th><th>Qty</th><th>Rate</th>${taxed ? '<th>Tax</th><th>Tax amt</th>' : ''}<th>Amount</th></tr>${rows}</table>
    ${taxed ? `<div class="muted">Tax included in the total: ${escapeHtml(formatRupees(inv.tax_paise))}</div>` : ''}
    <h2>Total ${escapeHtml(formatRupees(inv.total_paise))}</h2>
    ${credits}
    ${credits ? `<div><strong>Net ${escapeHtml(formatRupees(inv.net_paise))}</strong></div>` : ''}
    ${paid ? `<div class="muted">Received</div>${paid}` : ''}
    ${refunds}
    <div><strong>${inv.balance_paise > 0 ? `Balance due ${escapeHtml(formatRupees(inv.balance_paise))}` : 'Paid in full'}</strong></div>
    <div class="foot">Amounts and tax rates are as entered by the clinic. AarogyaOS does not decide what tax applies.</div>`);
}
