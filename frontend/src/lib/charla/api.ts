import { API_BASE, ApiError, request } from "@/lib/api";

import type {
  AnswerBody,
  AttendeeView,
  HideBody,
  PhoneBody,
  RegisterResponse,
  StatusResponse,
  UsernameCheck,
  VerifyResponse,
} from "./types";

/** ApiError(0): the request never got an answer (offline, DNS, timeout). */
export const OFFLINE_MESSAGE = "Sin conexión. Revisa tu internet e intenta de nuevo.";

/**
 * The shared request() speaks English for transport failures and FastAPI's 422s. Charla UI
 * copy is Spanish only, so swap those for Spanish; the backend's own `detail` passes as is.
 */
function toSpanish(error: unknown): unknown {
  if (!(error instanceof ApiError)) return error;
  if (error.status === 0) return new ApiError(0, OFFLINE_MESSAGE);
  if (error.status === 422) return new ApiError(422, "Revisa los datos e intenta de nuevo.");
  if (error.detail.startsWith("Request failed (")) {
    return new ApiError(error.status, `Algo falló en el servidor (${error.status}). Intenta de nuevo.`);
  }
  return error;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    return await request<T>(path, init);
  } catch (error) {
    throw toSpanish(error);
  }
}

const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });
const json = (body: unknown) => JSON.stringify(body);
const q = encodeURIComponent;

export const charlaApi = {
  checkUsername: (u: string, email?: string) =>
    call<UsernameCheck>(`/api/charla/username?u=${q(u)}${email ? `&email=${q(email)}` : ""}`),
  register: (username: string, email: string) =>
    call<RegisterResponse>("/api/charla/register", { method: "POST", body: json({ username, email }) }),
  status: (pending: string) => call<StatusResponse>(`/api/charla/register/status?p=${q(pending)}`),
  verify: (v: string) => call<VerifyResponse>("/api/charla/verify", { method: "POST", body: json({ v }) }),
  me: (token: string) => call<AttendeeView>("/api/charla/me", { headers: bearer(token) }),
  answer: (token: string, body: AnswerBody) =>
    call<{ accepted: true }>("/api/charla/answer", { method: "POST", headers: bearer(token), body: json(body) }),
  phone: (token: string, body: PhoneBody) =>
    call<{ ok: true }>("/api/charla/phone", { method: "POST", headers: bearer(token), body: json(body) }),
  /** SSE URL for EventSource, which can't send headers: the token rides in the query. */
  streamUrl: (token: string) => `${API_BASE}/api/charla/stream?t=${q(token)}`,
};

export type AdminApi = ReturnType<typeof adminApi>;

/** Presenter controls. Every call sends the key as X-Admin-Key; changes arrive over the admin stream. */
export function adminApi(key: string) {
  const post = (path: string, body?: unknown) =>
    call<{ ok: true }>(`/api/charla/admin/${path}`, {
      method: "POST",
      headers: { "X-Admin-Key": key },
      ...(body === undefined ? {} : { body: json(body) }),
    });
  return {
    launch: () => post("launch"),
    close: () => post("close"),
    reveal: () => post("reveal"),
    next: () => post("next"),
    goto: (step: number) => post("goto", { step }),
    resetStep: () => post("reset-step"),
    phoneNow: () => post("phone-now"),
    reclassify: () => post("reclassify"),
    verification: (on: boolean) => post("verification", { on }),
    hide: (body: HideBody) => post("hide", body),
    /** Wipes attendees and answers; the backend wants the literal confirmation. */
    reset: () => post("reset", { confirm: "RESET" }),
    /** Read-only key check: true when accepted, false on 401; throws ApiError otherwise (503 = no key configured). */
    check: () => checkAdminKey(key),
    /** For <a href download>; EventSource and plain links can't send headers. */
    exportUrl: `${API_BASE}/api/charla/admin/export.csv?key=${q(key)}`,
    streamUrl: `${API_BASE}/api/charla/admin/stream?key=${q(key)}`,
  };
}

/**
 * There is no read-only admin JSON endpoint, so probe the CSV export (a GET with no side
 * effects) and only look at the status code.
 */
async function checkAdminKey(key: string): Promise<boolean> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/charla/admin/export.csv`, { headers: { "X-Admin-Key": key } });
  } catch {
    throw new ApiError(0, OFFLINE_MESSAGE);
  }
  if (response.ok) return true;
  if (response.status === 401) return false;
  let detail = `Algo falló en el servidor (${response.status}). Intenta de nuevo.`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) detail = body.detail;
  } catch {
    // keep the generic message
  }
  throw new ApiError(response.status, detail);
}
