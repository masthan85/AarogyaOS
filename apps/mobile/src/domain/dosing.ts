/**
 * Reads the shorthand Indian prescribers write ("1-0-1", "BD", "TDS", "HS", "SOS") and says it in plain words.
 *
 * It only understands notation with one agreed meaning and returns null for anything else rather than
 * guessing. It never changes what the doctor typed on its own: the screen offers the wording and the doctor
 * chooses to use it. It does not read the dose itself, brand names or Indian-language phrases.
 */

export type ParsedFrequency = {
  /** The wording to put in the "how often" box. */
  text: string;
  /** Times a day, when the notation fixes it. */
  timesPerDay: number | null;
  /** True when each time means more or less than one dose (for example 2-0-2). The doctor must check the dose. */
  changesDose: boolean;
};

const WORDS: Record<string, ParsedFrequency> = {
  OD: { text: 'once daily', timesPerDay: 1, changesDose: false },
  QD: { text: 'once daily', timesPerDay: 1, changesDose: false },
  BD: { text: 'twice daily', timesPerDay: 2, changesDose: false },
  BID: { text: 'twice daily', timesPerDay: 2, changesDose: false },
  TDS: { text: 'three times daily', timesPerDay: 3, changesDose: false },
  TID: { text: 'three times daily', timesPerDay: 3, changesDose: false },
  QID: { text: 'four times daily', timesPerDay: 4, changesDose: false },
  QDS: { text: 'four times daily', timesPerDay: 4, changesDose: false },
  HS: { text: 'at bedtime', timesPerDay: 1, changesDose: false },
  SOS: { text: 'only when needed', timesPerDay: null, changesDose: false },
  PRN: { text: 'only when needed', timesPerDay: null, changesDose: false },
  STAT: { text: 'once, immediately', timesPerDay: null, changesDose: false },
};

const MEAL: Record<string, string> = { AC: 'before food', PC: 'after food' };

const SLOT_NAMES3 = ['morning', 'afternoon', 'night'];
const SLOT_NAMES4 = ['morning', 'afternoon', 'evening', 'night'];

const amount = (raw: string): number | null => {
  const v = raw.trim();
  if (v === '½' || v === '1/2') return 0.5;
  if (v === '¼' || v === '1/4') return 0.25;
  if (/^\d+(\.\d+)?$/.test(v)) return Number(v);
  if (/^\d+\s?½$/.test(v)) return parseInt(v, 10) + 0.5;
  return null;
};

const show = (n: number): string => (n === 0.5 ? '½' : n === 0.25 ? '¼' : String(n));

export function parseFrequency(input: string): ParsedFrequency | null {
  const raw = input.trim();
  if (!raw) return null;

  // "BD AC", "TDS PC": a frequency word, optionally with a meal word.
  const parts = raw.toUpperCase().split(/\s+/);
  if (parts.length <= 2 && WORDS[parts[0]]) {
    const base = WORDS[parts[0]];
    if (parts.length === 1) return base;
    const meal = MEAL[parts[1]];
    return meal ? { ...base, text: `${base.text}, ${meal}` } : null;
  }

  // "1-0-1" (morning, afternoon, night) or "1-0-0-1" (morning, afternoon, evening, night).
  const withMeal = raw.match(/^(.*?)(?:\s+(AC|PC))?$/i);
  const notation = (withMeal?.[1] ?? raw).replace(/\s+/g, '');
  const mealWord = withMeal?.[2];
  const m = notation.match(/^[^-]+(?:-[^-]+){2,3}$/);
  if (!m) return null;
  const slots = notation.split('-').map(amount);
  if (slots.some((s) => s === null)) return null;
  const nums = slots as number[];
  const names = nums.length === 3 ? SLOT_NAMES3 : SLOT_NAMES4;
  const used = nums.map((n, i) => ({ n, name: names[i] })).filter((x) => x.n > 0);
  if (used.length === 0) return null;
  const same = used.every((x) => x.n === used[0].n);
  const changesDose = !(same && used[0].n === 1);
  const when = used.map((x) => (same && used[0].n === 1 ? x.name : `${show(x.n)} in the ${x.name}`));
  const count = used.length;
  const times = count === 1 ? 'once daily' : count === 2 ? 'twice daily' : count === 3 ? 'three times daily' : 'four times daily';
  const meal = mealWord ? `, ${MEAL[mealWord.toUpperCase()]}` : '';
  const detail = same && used[0].n === 1 ? `${times}: ${when.join(' and ')}` : `${times}: ${when.join(', ')}`;
  return { text: `${detail}${meal}`, timesPerDay: count, changesDose };
}
