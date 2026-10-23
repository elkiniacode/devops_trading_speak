/**
 * What the charla pages remember in localStorage (CONTRACT §9.2). Every access is wrapped in
 * try/catch: private mode, blocked storage or a full quota must never break a page, they
 * just make it forget.
 */

const TOKEN_KEY = "charla.token";
const PENDING_KEY = "charla.pending";
const ADMIN_KEY = "charla.adminKey";
const MONITOR_KEY = "charla.monitorBase";

export const DEFAULT_MONITOR_BASE = "http://localhost:4800";

/** A registration waiting for its email link to be clicked. */
export interface PendingInfo {
  pending: string;
  email: string;
  username: string;
  /** Epoch ms of the last link sent, for the resend countdown. */
  sentAt: number;
}

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null || value === "") window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the value lives only as long as the page.
  }
}

// --- attendee session -----------------------------------------------------------------------

export const getToken = (): string | null => read(TOKEN_KEY) || null;
export const setToken = (token: string): void => write(TOKEN_KEY, token);
export const clearToken = (): void => write(TOKEN_KEY, null);

// --- pending registration -------------------------------------------------------------------

export function getPending(): PendingInfo | null {
  const raw = read(PENDING_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PendingInfo> | null;
    if (
      value &&
      typeof value.pending === "string" &&
      value.pending &&
      typeof value.email === "string" &&
      typeof value.username === "string" &&
      typeof value.sentAt === "number" &&
      Number.isFinite(value.sentAt)
    ) {
      return { pending: value.pending, email: value.email, username: value.username, sentAt: value.sentAt };
    }
  } catch {
    // corrupt JSON: treat as nothing pending
  }
  return null;
}

export function setPending(info: PendingInfo): void {
  write(PENDING_KEY, JSON.stringify({ pending: info.pending, email: info.email, username: info.username, sentAt: info.sentAt }));
}

export const clearPending = (): void => write(PENDING_KEY, null);

// --- presenter ------------------------------------------------------------------------------

export const getAdminKey = (): string | null => read(ADMIN_KEY) || null;
/** An empty string clears the key. */
export const setAdminKey = (key: string): void => write(ADMIN_KEY, key);
export const clearAdminKey = (): void => write(ADMIN_KEY, null);

/** Base URL of the agent-monitor dashboard, without a trailing slash. */
export const getMonitorBase = (): string => read(MONITOR_KEY) || DEFAULT_MONITOR_BASE;
export const setMonitorBase = (url: string): void => write(MONITOR_KEY, url.trim().replace(/\/+$/, ""));
