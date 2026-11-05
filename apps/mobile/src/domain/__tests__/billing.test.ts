import { draftTotal, draftTotals, emptyLine, lineTax, parsePercent, formatRupees, invoiceState, parseLines, parseRupees } from '../billing';

describe('formatRupees', () => {
  it('groups digits the Indian way and shows paise only when present', () => {
    expect(formatRupees(0)).toBe('₹0');
    expect(formatRupees(65000)).toBe('₹650');
    expect(formatRupees(49950)).toBe('₹499.50');
    expect(formatRupees(123456700)).toBe('₹12,34,567');
    expect(formatRupees(100000)).toBe('₹1,000');
    expect(formatRupees(10000000)).toBe('₹1,00,000');
    expect(formatRupees(5)).toBe('₹0.05');
  });
});

describe('parseRupees', () => {
  it('reads plain amounts into paise and refuses anything unclear', () => {
    expect(parseRupees('500')).toBe(50000);
    expect(parseRupees('₹ 1,250.5')).toBe(125050);
    expect(parseRupees('0.05')).toBe(5);
    for (const bad of ['', 'abc', '-5', '1.234', '1e3', '12,34.5.6', '100000000']) expect(parseRupees(bad)).toBeNull();
  });
});

describe('parseLines', () => {
  it('ignores blank rows, keeps good ones and names the first problem', () => {
    const ok = parseLines([{ description: 'Consultation', quantity: '1', price: '500', taxPct: '0' }, emptyLine(), { description: 'Dressing', quantity: '2', price: '75', taxPct: '0' }]);
    expect(ok.error).toBeUndefined();
    expect(ok.lines).toEqual([
      { description: 'Consultation', quantity: 1, unit_price_paise: 50000, tax_rate_bp: 0 },
      { description: 'Dressing', quantity: 2, unit_price_paise: 7500, tax_rate_bp: 0 },
    ]);
    expect(draftTotal(ok.lines)).toBe(65000);
    expect(parseLines([{ description: '', quantity: '1', price: '100', taxPct: '0' }]).error).toMatch(/Line 1: describe/);
    expect(parseLines([{ description: 'Dressing', quantity: '1', price: 'free', taxPct: '0' }]).error).toMatch(/amount/);
    expect(parseLines([{ description: 'Dressing', quantity: '0', price: '10', taxPct: '0' }]).error).toMatch(/quantity/);
    expect(parseLines([{ description: 'Dressing', quantity: '1.5', price: '10', taxPct: '0' }]).error).toMatch(/quantity/);
  });
});

describe('invoiceState', () => {
  it('says plainly where an invoice stands', () => {
    expect(invoiceState({ status: 'DRAFT', paid_paise: 0, balance_paise: 100 }).label).toBe('Draft');
    expect(invoiceState({ status: 'ISSUED', paid_paise: 0, balance_paise: 100 }).label).toBe('Unpaid');
    expect(invoiceState({ status: 'ISSUED', paid_paise: 40, balance_paise: 60 }).label).toBe('Part paid');
    expect(invoiceState({ status: 'ISSUED', paid_paise: 100, balance_paise: 0 }).label).toBe('Paid');
    expect(invoiceState({ status: 'VOID', paid_paise: 0, balance_paise: 0 }).label).toBe('Void');
  });
});

describe('tax', () => {
  it('reads percentages as basis points and refuses nonsense', () => {
    expect(parsePercent('')).toBe(0);
    expect(parsePercent('18')).toBe(1800);
    expect(parsePercent('2.5%')).toBe(250);
    for (const bad of ['29', 'abc', '-1', '1.234']) expect(parsePercent(bad)).toBeNull();
  });
  it('rounds each line half up, like the server', () => {
    expect(lineTax(3, 3333, 1800)).toBe(1800); // 17.9982 -> 18.00
    expect(lineTax(1, 50, 1000)).toBe(5);
    expect(lineTax(1, 5, 1000)).toBe(1); // 0.5 rounds up
    expect(draftTotals([{ quantity: 3, unit_price_paise: 3333, tax_rate_bp: 1800 }, { quantity: 1, unit_price_paise: 50000 }])).toEqual({ tax: 1800, total: 61799 });
  });
  it('rejects a bad tax rate on a line', () => {
    expect(parseLines([{ description: 'Test', quantity: '1', price: '10', taxPct: '40' }]).error).toMatch(/tax/);
  });
});
