import { ApiClient, ApiError } from '../client';
import { meSchema } from '../schemas';
import type { TokenStore, Tokens } from '@/services/token-store';

const me = {
  id: '1', organisation_id: 'o', email: 'a@b.com', full_name: 'A', roles: ['doctor'], permissions: [],
};
const pair = (n: number) => ({
  access_token: `access-${n}`, refresh_token: `refresh-${n}`, token_type: 'bearer', expires_in: 900,
});
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

function memoryStore(initial: Tokens | null): TokenStore & { current: Tokens | null } {
  const s = {
    current: initial,
    load: async () => s.current,
    save: async (t: Tokens) => { s.current = t; },
    clear: async () => { s.current = null; },
  };
  return s;
}

const base = { accessToken: 'access-0', refreshToken: 'refresh-0' };

describe('ApiClient', () => {
  it('attaches the bearer token', async () => {
    const fetchImpl = jest.fn(async () => json(200, me));
    const c = new ApiClient({ baseUrl: 'http://x', tokenStore: memoryStore(base), onSessionExpired: jest.fn(), fetchImpl });
    await c.request('/auth/me', meSchema);
    const init = (fetchImpl.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer access-0');
  });

  it('refreshes once on 401 and retries with the new token', async () => {
    const store = memoryStore(base);
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce(json(401, { detail: 'expired' }))
      .mockResolvedValueOnce(json(200, pair(1)))
      .mockResolvedValueOnce(json(200, me));
    const c = new ApiClient({ baseUrl: 'http://x', tokenStore: store, onSessionExpired: jest.fn(), fetchImpl });
    await expect(c.request('/auth/me', meSchema)).resolves.toMatchObject({ email: 'a@b.com' });
    expect(store.current).toEqual({ accessToken: 'access-1', refreshToken: 'refresh-1' });
  });

  it('shares a single refresh between concurrent 401s', async () => {
    const store = memoryStore(base);
    let refreshCalls = 0;
    const fetchImpl = jest.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/auth/refresh')) { refreshCalls += 1; return json(200, pair(1)); }
      const auth = (init?.headers as Record<string, string>).Authorization;
      return auth === 'Bearer access-1' ? json(200, me) : json(401, { detail: 'expired' });
    });
    const c = new ApiClient({ baseUrl: 'http://x', tokenStore: store, onSessionExpired: jest.fn(), fetchImpl: fetchImpl as unknown as typeof fetch });
    await Promise.all([c.request('/a', meSchema), c.request('/b', meSchema), c.request('/c', meSchema)]);
    expect(refreshCalls).toBe(1);
  });

  it('clears tokens and signals expiry when the refresh token is rejected', async () => {
    const store = memoryStore(base);
    const expired = jest.fn();
    const fetchImpl = jest.fn(async () => json(401, { detail: 'nope' }));
    const c = new ApiClient({ baseUrl: 'http://x', tokenStore: store, onSessionExpired: expired, fetchImpl });
    await expect(c.request('/auth/me', meSchema)).rejects.toBeInstanceOf(ApiError);
    expect(store.current).toBeNull();
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('keeps the session when the refresh fails because of the network', async () => {
    const store = memoryStore(base);
    const expired = jest.fn();
    const fetchImpl = jest
      .fn()
      .mockResolvedValueOnce(json(401, { detail: 'expired' }))
      .mockRejectedValueOnce(new TypeError('Network request failed'));
    const c = new ApiClient({ baseUrl: 'http://x', tokenStore: store, onSessionExpired: expired, fetchImpl });
    await expect(c.request('/auth/me', meSchema)).rejects.toBeInstanceOf(TypeError);
    expect(store.current).toEqual(base);
    expect(expired).not.toHaveBeenCalled();
  });

  it('rejects responses that do not match the schema', async () => {
    const fetchImpl = jest.fn(async () => json(200, { unexpected: true }));
    const c = new ApiClient({ baseUrl: 'http://x', tokenStore: memoryStore(base), onSessionExpired: jest.fn(), fetchImpl });
    await expect(c.request('/auth/me', meSchema)).rejects.toThrow();
  });

  it('surfaces server error detail and correlation id', async () => {
    const fetchImpl = jest.fn(async () =>
      new Response(JSON.stringify({ detail: 'Forbidden thing' }), { status: 403, headers: { 'x-request-id': 'abc' } }));
    const c = new ApiClient({ baseUrl: 'http://x', tokenStore: memoryStore(base), onSessionExpired: jest.fn(), fetchImpl });
    await expect(c.request('/x', meSchema)).rejects.toMatchObject({ status: 403, message: 'Forbidden thing', correlationId: 'abc' });
  });

  it('exposes the structured error body (e.g. duplicate candidates) on ApiError', async () => {
    const fetchImpl = jest.fn(async () =>
      new Response(JSON.stringify({ detail: 'Possible duplicate', candidates: [{ id: '1' }] }), { status: 409 }));
    const c = new ApiClient({ baseUrl: 'http://x', tokenStore: memoryStore(base), onSessionExpired: jest.fn(), fetchImpl });
    const err = await c.request('/patients', meSchema, { method: 'POST', body: {} }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.body?.candidates).toEqual([{ id: '1' }]);
  });

  it('downloads files with the same token handling and surfaces the server message on failure', async () => {
    const bytes = new Uint8Array([82, 73, 70, 70]);
    const ok = jest.fn(async () => new Response(bytes, { status: 200, headers: { 'content-type': 'audio/wav' } }));
    const c = new ApiClient({ baseUrl: 'http://x', tokenStore: memoryStore(base), onSessionExpired: jest.fn(), fetchImpl: ok });
    expect(Array.from(new Uint8Array(await c.requestBytes('/a', { method: 'POST', body: {} })))).toEqual([82, 73, 70, 70]);
    const init = (ok.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer access-0');

    const failing = jest.fn(async () => json(409, { detail: 'Only an approved document can be read aloud' }));
    const c2 = new ApiClient({ baseUrl: 'http://x', tokenStore: memoryStore(base), onSessionExpired: jest.fn(), fetchImpl: failing });
    await expect(c2.requestBytes('/a')).rejects.toMatchObject({ status: 409, message: 'Only an approved document can be read aloud' });
  });
});
