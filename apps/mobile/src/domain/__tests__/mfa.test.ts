import { ApiError } from '@/api/client';

import { groupSecret, looksLikeCode, needsSecondFactor, tidyCode, wrongSecondFactor } from '../mfa';

describe('second factor', () => {
  it('recognises the two server answers', () => {
    expect(needsSecondFactor(new ApiError(401, 'x', undefined, { title: 'mfa_required' }))).toBe(true);
    expect(needsSecondFactor(new ApiError(401, 'x', undefined, { title: 'unauthorized' }))).toBe(false);
    expect(needsSecondFactor(new ApiError(500, 'x', undefined, { title: 'mfa_required' }))).toBe(false);
    expect(wrongSecondFactor(new ApiError(401, 'x', undefined, { title: 'invalid_mfa_code' }))).toBe(true);
    expect(needsSecondFactor(new Error('network'))).toBe(false);
  });

  it('tidies and checks typed codes', () => {
    expect(tidyCode(' 123 456 ')).toBe('123456');
    expect(tidyCode('ABCDE-12345')).toBe('abcde-12345');
    expect(looksLikeCode('123 456')).toBe(true);
    expect(looksLikeCode('abcde-12345')).toBe(true);
    expect(looksLikeCode('12345')).toBe(false);
    expect(looksLikeCode('hello')).toBe(false);
  });

  it('groups the secret for typing', () => {
    expect(groupSecret('ABCDEFGHIJKL')).toBe('ABCD EFGH IJKL');
  });
});
