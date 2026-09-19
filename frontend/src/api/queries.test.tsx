import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { jobPollInterval, useActiveAnalysis } from "./queries";

const ACTIVE_JOB = {
  job_id: "job-9",
  status: "RUNNING",
  messages_total: 10,
  messages_processed: 3,
  progress_percent: 30,
  error_code: null,
  error_message: null,
  started_at: "2026-09-17T00:00:00Z",
  completed_at: null,
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    json: async () => body,
  } as Response;
}

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

function renderWithClient(node: ReactNode) {
  render(<QueryClientProvider client={makeClient()}>{node}</QueryClientProvider>);
}

function ActiveProbe() {
  const { data } = useActiveAnalysis();
  return (
    <div data-testid="active">{data ? (data.active?.job_id ?? "none") : "loading"}</div>
  );
}

describe("useActiveAnalysis", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the backend-active job so the dashboard can resume polling", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { active: ACTIVE_JOB }));
    renderWithClient(<ActiveProbe />);
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("job-9"));
  });

  it("queries the /api/analysis/active endpoint", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { active: null }));
    renderWithClient(<ActiveProbe />);
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("none"));
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/analysis/active"),
      expect.anything()
    );
  });

  it("reports none when the backend has no active job", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { active: null }));
    renderWithClient(<ActiveProbe />);
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("none"));
  });
});

describe("jobPollInterval", () => {
  it("keeps polling across every non-terminal status the backend uses", () => {
    for (const status of [
      "QUEUED",
      "RUNNING",
      "CLASSIFYING",
      "GROUPING",
      "BUILDING_RECOMMENDATIONS",
    ]) {
      expect(jobPollInterval(status)).toBe(2000);
    }
    expect(jobPollInterval(undefined)).toBe(2000);
  });

  it("stops polling once a job reaches a terminal status", () => {
    for (const status of ["COMPLETED", "FAILED", "CANCELLED"]) {
      expect(jobPollInterval(status)).toBe(false);
    }
  });
});