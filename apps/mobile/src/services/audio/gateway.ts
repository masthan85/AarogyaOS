import { API_BASE_URL } from '@/config';

/** Minimal slice of the WebSocket API we use, so tests can supply a fake. */
export interface SocketLike {
  binaryType: string;
  readyState: number;
  onopen: (() => void) | null;
  onmessage: ((e: { data: unknown }) => void) | null;
  onclose: ((e: { code: number; reason: string }) => void) | null;
  onerror: (() => void) | null;
  send(data: string | ArrayBuffer): void;
  close(code?: number, reason?: string): void;
}

export type GatewayEvent =
  | { type: 'ready' }
  | { type: 'stopped'; reason: string }
  | { type: 'closed'; code: number; reason: string };

type Options = {
  url: string;
  getToken: () => Promise<string>;
  onEvent: (e: GatewayEvent) => void;
  createSocket?: (url: string) => SocketLike;
};

const OPEN = 1;

export const toWebSocketUrl = (path: string, base: string = API_BASE_URL): string =>
  base.replace(/^http/, 'ws') + path;

export class GatewayClient {
  private socket: SocketLike | null = null;
  private ready = false;

  constructor(private readonly opts: Options) {}

  get isOpen(): boolean {
    return this.ready && this.socket?.readyState === OPEN;
  }

  /** Opens the socket, authenticates with the first message (never in the URL), resolves on 'ready'. */
  async connect(): Promise<void> {
    const token = await this.opts.getToken();
    const make = this.opts.createSocket ?? ((u: string) => new WebSocket(u) as unknown as SocketLike);
    const socket = make(this.opts.url);
    socket.binaryType = 'arraybuffer';
    this.socket = socket;

    await new Promise<void>((resolve, reject) => {
      socket.onopen = () => socket.send(JSON.stringify({ type: 'auth', token }));
      socket.onmessage = (e) => {
        const msg = parse(e.data);
        if (msg?.type === 'ready') {
          this.ready = true;
          this.opts.onEvent({ type: 'ready' });
          resolve();
        } else if (msg?.type === 'stopped') {
          this.opts.onEvent({ type: 'stopped', reason: String(msg.reason ?? '') });
        }
      };
      socket.onclose = (e) => {
        const wasReady = this.ready;
        this.ready = false;
        this.opts.onEvent({ type: 'closed', code: e.code, reason: e.reason });
        if (!wasReady) reject(new GatewayRefused(e.code, e.reason));
      };
      socket.onerror = () => {
        /* onclose follows with the code; nothing to add */
      };
    });
  }

  /** Returns false when the frame could not be sent, so callers can stop claiming to record. */
  sendAudio(frame: Uint8Array): boolean {
    if (!this.isOpen || !this.socket) return false;
    const buf = frame.buffer.slice(frame.byteOffset, frame.byteOffset + frame.byteLength) as ArrayBuffer;
    this.socket.send(buf);
    return true;
  }

  /** Ask the server to end the session cleanly. */
  stop(): void {
    if (this.isOpen && this.socket) this.socket.send(JSON.stringify({ type: 'stop' }));
  }

  close(): void {
    this.ready = false;
    this.socket?.close(1000);
    this.socket = null;
  }
}

export class GatewayRefused extends Error {
  constructor(
    readonly code: number,
    reason: string,
  ) {
    super(reason || `Connection closed (${code})`);
    this.name = 'GatewayRefused';
  }
}

function parse(data: unknown): { type?: string; reason?: unknown } | null {
  if (typeof data !== 'string') return null;
  try {
    const v = JSON.parse(data) as unknown;
    return typeof v === 'object' && v !== null ? (v as { type?: string; reason?: unknown }) : null;
  } catch {
    return null;
  }
}
