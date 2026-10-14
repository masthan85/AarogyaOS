import { can, roleLabel } from '../permissions';

const me = { id: '1', organisation_id: 'o', email: 'a@b.com', full_name: 'A', roles: ['doctor'], permissions: ['facility:read'] };

describe('permissions helpers', () => {
  it('checks permissions', () => {
    expect(can(me, 'facility:read')).toBe(true);
    expect(can(me, 'user:manage')).toBe(false);
    expect(can(null, 'facility:read')).toBe(false);
  });
  it('labels roles with a safe fallback', () => {
    expect(roleLabel('doctor')).toBe('Doctor');
    expect(roleLabel('something_new')).toBe('something_new');
  });
});
