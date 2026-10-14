import type { z } from 'zod';

import type { TokenStore, Tokens } from '@/services/token-store';

import { tokenPairSchema } from './schemas';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly correlationId?: string,
    /** Parsed error body, e.g. duplicate-patient candidates. Never log it: it may hold PHI. */
    readonly body?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

type Options = {
  baseUrl: string;
  tokenStore: TokenStore;
  /** Called when the refresh token is rejected; the UI should return to sign-in. */
  onSessionExpired: () => void;
  fetchImpl?: typeof fetch;
};

type RequestInitLite = { method?: string; body?: unknown; auth?: boolean };

export class ApiClient {
  private refreshing: Promise<Tokens | null> | null = null;
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly opts: Options) {
    this.fetchImpl = opts.fetchImpl ?? fetch;
  }

  async request<S extends z.ZodType>(
    path: string,
    schema: S,
    init: RequestInitLite = {},
  ): Promise<z.infer<S>> {
    const auth = init.auth ?? true;
    let tokens = auth ? await this.opts.tokenStore.load() : null;
    if (auth && !tokens) throw new ApiError(401, 'Not signed in');

    let res = await this.send(path, init, tokens?.accessToken);
    if (res.status === 401 && auth && tokens) {
      // Share one refresh between concurrent requests: refresh tokens rotate, and a
      // second concurrent use of the same token would look like theft to the server.
      tokens = await this.refreshOnce(tokens);
      if (!tokens) throw new ApiError(401, 'Session expired');
      res = await this.send(path, init, tokens.accessToken);
    }
    return this.parse(res, schema);
  }

  private async send(path: string, init: RequestInitLite, accessToken?: string): Promise<Response> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (init.body !== undefined) headers['Content-Type'] = 'application/json';
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    return this.fetchImpl(`${this.opts.baseUrl}${path}`, {
      method: init.method ?? 'GET',
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
  }

  private refreshOnce(stale: Tokens): Promise<Tokens | null> {
    if (!this.refreshing) {
      this.refreshing = this.doRefresh(stale).finally(() => {
        this.refreshing = null;
      });
    }
    return this.refreshing;
  }

  private async doRefresh(stale: Tokens): Promise<Tokens | null> {
    try {
      const res = await this.send('/auth/refresh', {
        method: 'POST',
        body: { refresh_token: stale.refreshToken },
      });
      if (res.status === 401) throw new ApiError(401, 'refresh rejected');
      const pair = await this.parse(res, tokenPairSchema);
      const next = { accessToken: pair.access_token, refreshToken: pair.refresh_token };
      await this.opts.tokenStore.save(next);
      return next;
    } catch (err) {
      // Only a definite rejection ends the session. A network blip must not sign a nurse
      // out mid-shift; the original request simply fails and can be retried.
      if (err instanceof ApiError && err.status === 401) {
        await this.opts.tokenStore.clear();
        this.opts.onSessionExpired();
      } else {
        throw err;
      }
      return null;
    }
  }

  private async parse<S extends z.ZodType>(res: Response, schema: S): Promise<z.infer<S>> {
    const correlationId = res.headers.get('x-request-id') ?? undefined;
    if (!res.ok) {
      let detail = `Request failed (${res.status})`;
      let parsed: Record<string, unknown> | undefined;
      try {
        parsed = (await res.json()) as Record<string, unknown>;
        if (typeof parsed.detail === 'string') detail = parsed.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(res.status, detail, correlationId, parsed);
    }
    if (res.status === 204) return schema.parse(undefined);
    return schema.parse(await res.json());
  }
}
