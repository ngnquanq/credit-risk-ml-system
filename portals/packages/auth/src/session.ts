import { randomBytes } from "node:crypto";
import { Redis } from "ioredis";

export { SESSION_COOKIE } from "./cookies";

export interface Session {
  sub: string;
  name?: string;
  roles: string[];
  branchId?: string | null;
  accessToken: string;
  refreshToken?: string;
  idToken?: string;
  /** Epoch seconds when the access token expires. */
  expiresAt: number;
  /** Epoch seconds when the session started (absolute timeout). */
  createdAt: number;
  csrfToken: string;
}

export interface PendingLogin {
  codeVerifier: string;
  nonce: string;
  returnTo: string;
}

/** Key-value operations the store needs; Redis in production, a Map in tests. */
export interface KeyValue {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, mode: "EX", seconds: number): Promise<unknown>;
  expire(key: string, seconds: number): Promise<unknown>;
  del(key: string): Promise<unknown>;
  getdel?(key: string): Promise<string | null>;
}

export function randomToken(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

export class SessionStore {
  constructor(
    private readonly kv: KeyValue,
    private readonly idleTimeout: number,
    private readonly absoluteTimeout: number,
    private readonly now: () => number = () => Math.floor(Date.now() / 1000),
  ) {}

  static fromUrl(url: string, idleTimeout: number, absoluteTimeout: number): SessionStore {
    return new SessionStore(new Redis(url, { lazyConnect: false, maxRetriesPerRequest: 2 }), idleTimeout, absoluteTimeout);
  }

  async create(data: Omit<Session, "createdAt" | "csrfToken">): Promise<{ id: string; session: Session }> {
    const id = randomToken();
    const session: Session = { ...data, createdAt: this.now(), csrfToken: randomToken() };
    await this.kv.set(`sess:${id}`, JSON.stringify(session), "EX", this.idleTimeout);
    return { id, session };
  }

  /** Returns the session and slides the idle timeout, or null when expired or unknown. */
  async get(id: string | undefined): Promise<Session | null> {
    if (!id) return null;
    const raw = await this.kv.get(`sess:${id}`);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (this.now() - session.createdAt > this.absoluteTimeout) {
      await this.destroy(id);
      return null;
    }
    await this.kv.expire(`sess:${id}`, this.idleTimeout);
    return session;
  }

  async update(id: string, session: Session): Promise<void> {
    await this.kv.set(`sess:${id}`, JSON.stringify(session), "EX", this.idleTimeout);
  }

  async destroy(id: string): Promise<void> {
    await this.kv.del(`sess:${id}`);
  }

  async savePendingLogin(state: string, pending: PendingLogin): Promise<void> {
    await this.kv.set(`login:${state}`, JSON.stringify(pending), "EX", 600);
  }

  /** One-time read: a state value can complete at most one login. */
  async takePendingLogin(state: string): Promise<PendingLogin | null> {
    const key = `login:${state}`;
    const raw = this.kv.getdel ? await this.kv.getdel(key) : await this.kv.get(key);
    if (!this.kv.getdel) await this.kv.del(key);
    return raw ? (JSON.parse(raw) as PendingLogin) : null;
  }
}
