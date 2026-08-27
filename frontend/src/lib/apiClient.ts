import type { ApiErrorBody } from "@/types/api";

/**
 * Centralized fetch wrapper for the MailSweep backend.
 *
 * Auth & CSRF
 *   - Sessions ride on an HttpOnly cookie (`mailsweep_session`), so every
 *     request uses `credentials: "include"`. Never store tokens in the client.
 *   - During dev the Vite proxy forwards `/api` to the backend same-origin, so
 *     CSRF Origin checks pass without custom headers.
 *
 * Errors
 *   - Any non-2xx is thrown as an {@link ApiError} carrying the backend's
 *     envelope (`code`, `message`, `request_id`).
 *   - A 401 also emits a window event so the auth layer can drop the session.
 */

export const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
    requestId?: string | null
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId ?? null;
  }

  get isAuth() {
    return this.status === 401 || this.status === 403;
  }
  get isNotFound() {
    return this.status === 404;
  }
  get isRateLimited() {
    return this.status === 429;
  }
}

/** Fired on any 401/403 so the app can transition to the signed-out state. */
export const SESSION_EXPIRED_EVENT = "mailsweep:session-expired";

function notifySessionExpired() {
  window.dispatchEvent(new CustomEvent(SESSION_EXPIRED_EVENT));
}

export interface ApiOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

/**
 * Thin fetch wrapper: JSON in/out, credentials included, typed errors.
 * Never used directly by components — prefer the endpoint modules + hooks.
 */
export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { body, headers, ...rest } = options;

  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      // Echo a unique request id so the app can correlate with backend logs.
      "X-Request-ID": crypto.randomUUID(),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!res.ok) {
    let bodyErr: ApiErrorBody | null = null;
    try {
      bodyErr = (await res.json()) as ApiErrorBody;
    } catch {
      bodyErr = null;
    }
    const code = bodyErr?.error?.code ?? `http_${res.status}`;
    const message = bodyErr?.error?.message ?? res.statusText;
    const error = new ApiError(
      res.status,
      code,
      message,
      bodyErr?.error?.details,
      bodyErr?.request_id
    );
    if (error.isAuth) notifySessionExpired();
    throw error;
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Build a query string from a record, dropping null/undefined/empty values. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}