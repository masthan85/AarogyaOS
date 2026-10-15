import type { ClinicalDocument, Prescription } from '@/api/schemas';

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
