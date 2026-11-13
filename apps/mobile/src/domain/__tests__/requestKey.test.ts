import { newRequestKey } from '../requestKey';

describe('newRequestKey', () => {
  it('fits what the server accepts and does not repeat', () => {
    const keys = new Set(Array.from({ length: 500 }, newRequestKey));
    expect(keys.size).toBe(500);
    for (const k of keys) {
      expect(k.length).toBeGreaterThanOrEqual(8);
      expect(k.length).toBeLessThanOrEqual(100);
      expect(k).toMatch(/^[a-z0-9-]+$/);
    }
  });
});
