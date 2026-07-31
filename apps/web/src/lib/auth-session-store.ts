import { randomBytes, timingSafeEqual } from "node:crypto";

export interface OidcTransaction {
  state: string;
  nonce: string;
  codeVerifier: string;
  returnTo: string;
}

interface StoredTransaction extends OidcTransaction {
  expiresAt: number;
}

export interface SessionTokens {
  accessToken: string;
  accessTokenExpiresAt: number;
  refreshToken?: string;
  idToken?: string;
}

export interface WebSession extends SessionTokens {
  id: string;
  subject: string;
  csrfToken: string;
  createdAt: number;
  lastSeenAt: number;
  absoluteExpiresAt: number;
}

export interface SessionStoreOptions {
  absoluteLifetimeMilliseconds: number;
  inactivityLifetimeMilliseconds: number;
  transactionLifetimeMilliseconds: number;
  maximumEntries?: number;
  randomIdentifier?: () => string;
}

function secureIdentifier(): string {
  return randomBytes(32).toString("base64url");
}

export class SessionStore {
  private readonly transactions = new Map<string, StoredTransaction>();
  private readonly sessions = new Map<string, WebSession>();
  private readonly maximumEntries: number;
  private readonly randomIdentifier: () => string;

  constructor(private readonly options: SessionStoreOptions) {
    if (
      options.absoluteLifetimeMilliseconds <= 0 ||
      options.inactivityLifetimeMilliseconds <= 0 ||
      options.transactionLifetimeMilliseconds <= 0
    ) {
      throw new RangeError("Session lifetimes must be positive.");
    }
    this.maximumEntries = options.maximumEntries ?? 2_048;
    if (this.maximumEntries < 1) {
      throw new RangeError("Session capacity must be positive.");
    }
    this.randomIdentifier = options.randomIdentifier ?? secureIdentifier;
  }

  createTransaction(transaction: OidcTransaction, now: number): string {
    this.prune(now);
    this.requireCapacity(this.transactions);
    const id = this.uniqueIdentifier(this.transactions);
    this.transactions.set(id, {
      ...transaction,
      expiresAt: now + this.options.transactionLifetimeMilliseconds,
    });
    return id;
  }

  consumeTransaction(
    id: string | undefined,
    now: number,
  ): OidcTransaction | null {
    if (id === undefined) {
      return null;
    }
    const transaction = this.transactions.get(id);
    this.transactions.delete(id);
    if (transaction === undefined || transaction.expiresAt <= now) {
      return null;
    }
    return {
      state: transaction.state,
      nonce: transaction.nonce,
      codeVerifier: transaction.codeVerifier,
      returnTo: transaction.returnTo,
    };
  }

  createSession(
    tokens: SessionTokens,
    subject: string,
    now: number,
  ): WebSession {
    this.prune(now);
    this.requireCapacity(this.sessions);
    const id = this.uniqueIdentifier(this.sessions);
    const session: WebSession = {
      ...tokens,
      id,
      subject,
      csrfToken: this.randomIdentifier(),
      createdAt: now,
      lastSeenAt: now,
      absoluteExpiresAt: now + this.options.absoluteLifetimeMilliseconds,
    };
    this.sessions.set(id, session);
    return { ...session };
  }

  getSession(
    id: string | undefined,
    now: number,
    touch = true,
  ): WebSession | null {
    if (id === undefined) {
      return null;
    }
    const session = this.sessions.get(id);
    if (session === undefined) {
      return null;
    }
    if (
      session.absoluteExpiresAt <= now ||
      session.lastSeenAt + this.options.inactivityLifetimeMilliseconds <= now
    ) {
      this.sessions.delete(id);
      return null;
    }
    if (touch) {
      session.lastSeenAt = now;
    }
    return { ...session };
  }

  replaceTokens(
    id: string,
    tokens: SessionTokens,
    now: number,
  ): WebSession | null {
    const session = this.getSession(id, now, false);
    if (session === null) {
      return null;
    }
    const updated: WebSession = {
      ...session,
      ...tokens,
      lastSeenAt: now,
    };
    this.sessions.set(id, updated);
    return { ...updated };
  }

  deleteSession(id: string | undefined): void {
    if (id !== undefined) {
      this.sessions.delete(id);
    }
  }

  csrfMatches(session: WebSession, candidate: string | null): boolean {
    if (candidate === null) {
      return false;
    }
    const expected = Buffer.from(session.csrfToken);
    const received = Buffer.from(candidate);
    return (
      expected.length === received.length && timingSafeEqual(expected, received)
    );
  }

  private prune(now: number): void {
    for (const [id, transaction] of this.transactions) {
      if (transaction.expiresAt <= now) {
        this.transactions.delete(id);
      }
    }
    for (const [id, session] of this.sessions) {
      if (
        session.absoluteExpiresAt <= now ||
        session.lastSeenAt + this.options.inactivityLifetimeMilliseconds <= now
      ) {
        this.sessions.delete(id);
      }
    }
  }

  private requireCapacity<T>(entries: Map<string, T>): void {
    if (entries.size < this.maximumEntries) {
      return;
    }
    const oldest = entries.keys().next().value;
    if (oldest !== undefined) {
      entries.delete(oldest);
    }
  }

  private uniqueIdentifier<T>(entries: Map<string, T>): string {
    for (let attempt = 0; attempt < 8; attempt += 1) {
      const candidate = this.randomIdentifier();
      if (candidate.length >= 32 && !entries.has(candidate)) {
        return candidate;
      }
    }
    throw new Error("A unique session identifier could not be generated.");
  }
}
