import { arrange, DASHBOARD_ACTIONS, greeting } from '../actions';

describe('arrange', () => {
  it('shows only permitted tiles, grouped in a fixed order, and drops empty headings', () => {
    const nurse = arrange(DASHBOARD_ACTIONS, (p) => ['queue:read', 'patient:search'].includes(p));
    expect(nurse.map((g) => g.group)).toEqual(['today']);
    expect(nurse[0].actions.map((a) => a.key)).toEqual(['queue', 'patients']);
    const admin = arrange(DASHBOARD_ACTIONS, () => true);
    expect(admin.map((g) => g.group)).toEqual(['today', 'clinical', 'manage']);
    expect(arrange(DASHBOARD_ACTIONS, () => false)).toEqual([]);
  });
  it('gives every tile a working destination and a unique key', () => {
    expect(new Set(DASHBOARD_ACTIONS.map((a) => a.key)).size).toBe(DASHBOARD_ACTIONS.length);
    expect(DASHBOARD_ACTIONS.every((a) => a.href)).toBe(true);
  });
});

describe('greeting', () => {
  it('follows the hour of the day', () => {
    expect([2, 9, 13, 18, 23].map(greeting)).toEqual([
      'Good evening', 'Good morning', 'Good afternoon', 'Good evening', 'Good evening',
    ]);
  });
});
