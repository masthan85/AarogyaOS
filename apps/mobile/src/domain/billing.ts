import type { Invoice } from '@/api/schemas';

/** ₹ with Indian digit grouping (12,34,567), showing paise only when there are some. */
export function formatRupees(paise: number): string {
  const negative = paise < 0;
  const abs = Math.abs(Math.round(paise));
  const rupees = Math.floor(abs / 100);
  const rest = abs % 100;
  const digits = String(rupees);
  const grouped = digits.length <= 3 ? digits : `${digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',')},${digits.slice(-3)}`;
  return `${negative ? '-' : ''}₹${grouped}${rest ? `.${String(rest).padStart(2, '0')}` : ''}`;
}

/** What a person typed into an amount box, in whole paise, or null when it is not a usable amount. */
export function parseRupees(text: string): number | null {
  const t = text.trim().replace(/^₹\s*/, '').replace(/,/g, '');
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  const [r, p = ''] = t.split('.');
  const paise = Number(r) * 100 + Number(p.padEnd(2, '0'));
  return Number.isSafeInteger(paise) && paise <= 10_000_000_00 ? paise : null;
}

export type LineDraft = { description: string; quantity: string; price: string; taxPct: string };
export const emptyLine = (): LineDraft => ({ description: '', quantity: '1', price: '', taxPct: '0' });

/** A tax percentage typed as 18 or 2.5, as basis points (1800, 250), or null when unusable. */
export function parsePercent(text: string): number | null {
  const t = text.trim().replace(/%$/, '');
  if (t === '') return 0;
  if (!/^\d{1,2}(\.\d{1,2})?$/.test(t)) return null;
  const bp = Math.round(Number(t) * 100);
  return bp >= 0 && bp <= 2800 ? bp : null;
}

/** Tax on one line in whole paise, rounded half up (the same rule the server uses). */
export const lineTax = (quantity: number, unitPaise: number, rateBp: number): number =>
  Math.floor((quantity * unitPaise * rateBp + 5000) / 10000);

export type ParsedLines = { lines: { description: string; quantity: number; unit_price_paise: number; tax_rate_bp: number }[]; error?: string };

/** Turns the typed lines into what the server takes. Blank rows are ignored; a half-filled row is an error. */
export function parseLines(drafts: LineDraft[]): ParsedLines {
  const lines: ParsedLines['lines'] = [];
  for (const [i, d] of drafts.entries()) {
    const description = d.description.trim();
    if (!description && !d.price.trim()) continue;
    if (description.length < 2) return { lines, error: `Line ${i + 1}: describe the charge.` };
    const price = parseRupees(d.price);
    if (price === null) return { lines, error: `Line ${i + 1}: enter the amount in rupees, for example 500 or 499.50.` };
    const quantity = Number(d.quantity.trim() || '1');
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 999) return { lines, error: `Line ${i + 1}: quantity must be a whole number from 1 to 999.` };
    const rate = parsePercent(d.taxPct);
    if (rate === null) return { lines, error: `Line ${i + 1}: tax must be a percentage from 0 to 28.` };
    lines.push({ description, quantity, unit_price_paise: price, tax_rate_bp: rate });
  }
  return { lines };
}

type Priced = { quantity: number; unit_price_paise: number; tax_rate_bp?: number };

/** Tax and grand total (tax included) for typed lines. */
export function draftTotals(lines: Priced[]): { tax: number; total: number } {
  let tax = 0;
  let net = 0;
  for (const l of lines) {
    net += l.quantity * l.unit_price_paise;
    tax += lineTax(l.quantity, l.unit_price_paise, l.tax_rate_bp ?? 0);
  }
  return { tax, total: net + tax };
}
export const draftTotal = (lines: Priced[]): number => draftTotals(lines).total;

/** "18%" or "2.5%" from basis points. */
export const percentLabel = (bp: number): string => `${bp / 100}%`;

export type InvoiceState = { label: string; tone: 'neutral' | 'success' | 'warning' | 'danger' };

export function invoiceState(inv: Pick<Invoice, 'status' | 'paid_paise' | 'balance_paise'>): InvoiceState {
  if (inv.status === 'DRAFT') return { label: 'Draft', tone: 'neutral' };
  if (inv.status === 'VOID') return { label: 'Void', tone: 'danger' };
  if (inv.balance_paise <= 0) return { label: 'Paid', tone: 'success' };
  return inv.paid_paise > 0 ? { label: 'Part paid', tone: 'warning' } : { label: 'Unpaid', tone: 'warning' };
}

export const METHOD_LABELS: Record<string, string> = { CASH: 'Cash', UPI: 'UPI', CARD: 'Card', INSURER: 'Insurer', OTHER: 'Other' };
