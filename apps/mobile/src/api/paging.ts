/**
 * Paging for lists the API serves newest first. A full page means there may be more: the next page
 * starts after the last row received. A short page is the end.
 */
export function nextBefore<T extends { id: string }>(page: T[], size: number): string | undefined {
  return page.length === size ? page[page.length - 1]?.id : undefined;
}

/** All pages in order, without a row twice if a refresh and a "show older" overlapped. */
export function flatten<T extends { id: string }>(pages: T[][] | undefined): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const page of pages ?? []) for (const row of page) if (!seen.has(row.id)) { seen.add(row.id); out.push(row); }
  return out;
}
