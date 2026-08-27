import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, qs, SESSION_EXPIRED_EVENT } from "./apiClient";

function mockResponse(init: {
  status?: number;
  statusText?: string;
  body?: unknown;
}): Response {
  const { status = 200, statusText = "OK", body } = init;
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body ?? "")),
  } as unknown as Response;
}

describe("qs", () => {
  it("builds a query string from present values", () => {
    expect(qs({ page: 1, risk: "LOW", q: "" })).toBe("?page=1&risk=LOW");
  });
  it("returns empty string when all values are empty", () => {
    expect(qs({ a: null, b: undefined, c: "" })).toBe("");
  });
});

describe("apiFetch", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  it("returns parsed JSON on 2xx and includes credentials", async () => {
    fetchMock.mockResolvedValue(mockResponse({ status: 200, body: { ok: true } }));
    const data = await apiFetch<{ ok: boolean }>("/api/health");
    expect(data).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/health");
    expect(init.credentials).toBe("include");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
  });

  it("throws ApiError with backend envelope on error responses", async () => {
    fetchMock.mockResolvedValue(
      mockResponse({
        status: 404,
        statusText: "Not Found",
        body: { error: { code: "not_found", message: "Nope" }, request_id: "r1" },
      })
    );
    const err = await apiFetch("/api/missing").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).code).toBe("not_found");
    expect((err as ApiError).requestId).toBe("r1");
    expect((err as ApiError).isNotFound).toBe(true);
  });

  it("fires SESSION_EXPIRED_EVENT on 401", async () => {
    const spy = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, spy);
    fetchMock.mockResolvedValue(mockResponse({ status: 401, statusText: "Unauthorized" }));
    await apiFetch("/api/auth/status").catch(() => undefined);
    expect(spy).toHaveBeenCalledTimes(1);
    window.removeEventListener(SESSION_EXPIRED_EVENT, spy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });
});
