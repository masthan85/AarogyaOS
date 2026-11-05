const pad = (n: number) => String(n).padStart(2, '0');

/** YYYY-MM-DD in the device's local calendar (clinic staff are on local time). */
export const toDateString = (d: Date): string =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export const addDays = (d: Date, days: number): Date => {
  const next = new Date(d);
  next.setDate(next.getDate() + days);
  return next;
};

export const formatTime = (iso: string): string =>
  new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });

export const formatDay = (d: Date): string =>
  d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' });

export const formatDateTime = (iso: string): string =>
  new Date(iso).toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  });

/** A date-only value such as 2026-11-04, shown as "4 Nov 2026" without any timezone shift. */
export const formatDate = (isoDate: string): string => {
  const [y, m, d] = isoDate.split('-').map(Number);
  if (!y || !m || !d) return isoDate;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
  });
};
