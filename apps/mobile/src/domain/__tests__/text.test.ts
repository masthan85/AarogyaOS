import { sentence } from '../text';

describe('sentence', () => {
  it('turns stored codes into readable words', () => {
    expect(sentence('IN_CONSULTATION')).toBe('In consultation');
    expect(sentence('ACTIVE')).toBe('Active');
    expect(sentence('login success')).toBe('Login success');
    expect(sentence('')).toBe('');
  });
});
