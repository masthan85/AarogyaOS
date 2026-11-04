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

export type LineDraft = { description: string; quantity: string; price: string };
export const emptyLine = (): LineDraft => ({ description: '', quantity: '1', price: '' });

export type ParsedLines = { lines: { description: string; quantity: number; unit_price_paise: number }[]; error?: string };

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
    lines.push({ description, quantity, unit_price_paise: price });
  }
  return { lines };
}

export const draftTotal = (lines: { quantity: number; unit_price_paise: number }[]): number =>
  lines.reduce((sum, l) => sum + l.quantity * l.unit_price_paise, 0);

export type InvoiceState = { label: string; tone: 'neutral' | 'success' | 'warning' | 'danger' };

export function invoiceState(inv: Pick<Invoice, 'status' | 'paid_paise' | 'balance_paise'>): InvoiceState {
  if (inv.status === 'DRAFT') return { label: 'Draft', tone: 'neutral' };
  if (inv.status === 'VOID') return { label: 'Void', tone: 'danger' };
  if (inv.balance_paise <= 0) return { label: 'Paid', tone: 'success' };
  return inv.paid_paise > 0 ? { label: 'Part paid', tone: 'warning' } : { label: 'Unpaid', tone: 'warning' };
}

export const METHOD_LABELS: Record<string, string> = { CASH: 'Cash', UPI: 'UPI', CARD: 'Card', OTHER: 'Other' };
