import { GatewayClient, GatewayRefused, type GatewayEvent, type SocketLike, toWebSocketUrl } from '../gateway';

class FakeSocket implements SocketLike {
  binaryType = 'blob';
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onclose: ((e: { code: number; reason: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  sent: (string | ArrayBuffer)[] = [];
  constructor(readonly url: string) {}
  send(d: string | ArrayBuffer) { this.sent.push(d); }
  close() { this.readyState = 3; }
  // test helpers
  open() { this.readyState = 1; this.onopen?.(); }
  receive(obj: unknown) { this.onmessage?.({ data: JSON.stringify(obj) }); }
  drop(code: number, reason = '') { this.readyState = 3; this.onclose?.({ code, reason }); }
}

function setup() {
  const events: GatewayEvent[] = [];
  let socket!: FakeSocket;
  const client = new GatewayClient({
    url: 'ws://host/api/v1/interactions/abc/audio',
    getToken: async () => 'SECRET-TOKEN',
    onEvent: (e) => events.push(e),
    createSocket: (u) => (socket = new FakeSocket(u)),
  });
  return { client, events, sock: () => socket };
}

describe('GatewayClient', () => {
  it('authenticates with the first message and keeps the token out of the URL', async () => {
    const { client, sock } = setup();
    const connecting = client.connect();
    await Promise.resolve();
    sock().open();
    expect(sock().url).not.toContain('SECRET-TOKEN');
    expect(JSON.parse(sock().sent[0] as string)).toEqual({ type: 'auth', token: 'SECRET-TOKEN' });
    sock().receive({ type: 'ready' });
    await connecting;
    expect(client.isOpen).toBe(true);
    expect(sock().binaryType).toBe('arraybuffer');
  });

  it('does not send audio until the server is ready, and says so', async () => {
    const { client, sock } = setup();
    const connecting = client.connect();
    await Promise.resolve();
    sock().open();
    expect(client.sendAudio(new Uint8Array(4))).toBe(false);
    sock().receive({ type: 'ready' });
    await connecting;
    expect(client.sendAudio(new Uint8Array([1, 2, 3, 4]))).toBe(true);
    expect(sock().sent).toHaveLength(2);
  });

  it('sends exactly the bytes of a sub-view, not the whole backing buffer', async () => {
    const { client, sock } = setup();
    const connecting = client.connect();
    await Promise.resolve();
    sock().open();
    sock().receive({ type: 'ready' });
    await connecting;
    const backing = new Uint8Array([9, 9, 1, 2, 3, 4, 9, 9]);
    client.sendAudio(backing.subarray(2, 6));
    const sent = sock().sent[1] as ArrayBuffer;
    expect(Array.from(new Uint8Array(sent))).toEqual([1, 2, 3, 4]);
  });

  it('rejects with the close code when the server refuses the connection', async () => {
    const { client, sock } = setup();
    const connecting = client.connect();
    await Promise.resolve();
    sock().open();
    sock().drop(4403, 'consent missing');
    await expect(connecting).rejects.toMatchObject({ name: 'GatewayRefused', code: 4403 });
    await expect(connecting).rejects.toBeInstanceOf(GatewayRefused);
  });

  it('reports a later drop and stops claiming to be open', async () => {
    const { client, sock, events } = setup();
    const connecting = client.connect();
    await Promise.resolve();
    sock().open();
    sock().receive({ type: 'ready' });
    await connecting;
    sock().drop(1006);
    expect(client.isOpen).toBe(false);
    expect(client.sendAudio(new Uint8Array(2))).toBe(false);
    expect(events.at(-1)).toEqual({ type: 'closed', code: 1006, reason: '' });
  });

  it('forwards the server stop reason and can request a clean stop', async () => {
    const { client, sock, events } = setup();
    const connecting = client.connect();
    await Promise.resolve();
    sock().open();
    sock().receive({ type: 'ready' });
    await connecting;
    client.stop();
    expect(JSON.parse(sock().sent.at(-1) as string)).toEqual({ type: 'stop' });
    sock().receive({ type: 'stopped', reason: 'CONSENT_WITHDRAWN' });
    expect(events).toContainEqual({ type: 'stopped', reason: 'CONSENT_WITHDRAWN' });
  });

  it('ignores malformed server messages', async () => {
    const { client, sock } = setup();
    const connecting = client.connect();
    await Promise.resolve();
    sock().open();
    sock().onmessage?.({ data: 'not json' });
    sock().onmessage?.({ data: new ArrayBuffer(2) });
    sock().receive({ type: 'ready' });
    await expect(connecting).resolves.toBeUndefined();
  });

  it('builds ws and wss URLs', () => {
    expect(toWebSocketUrl('/x', 'http://10.0.2.2:8000')).toBe('ws://10.0.2.2:8000/x');
    expect(toWebSocketUrl('/x', 'https://api.example.in')).toBe('wss://api.example.in/x');
  });
});
