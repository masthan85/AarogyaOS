import { flatten, nextBefore } from '../paging';

const rows = (...ids: string[]) => ids.map((id) => ({ id }));

describe('paging', () => {
  it('asks for more only after a full page, starting after its last row', () => {
    expect(nextBefore(rows('c', 'b'), 2)).toBe('b');
    expect(nextBefore(rows('a'), 2)).toBeUndefined();
    expect(nextBefore([], 2)).toBeUndefined();
  });

  it('joins pages in order and never shows a row twice', () => {
    expect(flatten([rows('d', 'c'), rows('c', 'b'), rows('a')]).map((r) => r.id)).toEqual(['d', 'c', 'b', 'a']);
    expect(flatten(undefined)).toEqual([]);
  });
});
