import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({
    status: {
      authenticated: true,
      user: { id: "u1", email: "you@example.com", display_name: "You", avatar_url: null },
      gmail_connection: {
        connected: true,
        email: "you@example.com",
        status: "ACTIVE",
        connected_at: null,
        granted_scopes: [],
      },
    },
  }),
}));

const QUEUED_JOB = {
  job_id: "job-1",
  status: "QUEUED",
  messages_total: null,
  messages_processed: 0,
  progress_percent: null,
  error_code: null,
  error_message: null,
  started_at: null,
  completed_at: null,
};

const WITHOUT_SUMMARY = {
  gmail_connection: { connected: true, email: "you@example.com" },
  analyzed: false,
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "OK",
    json: async () => body,
  } as Response;
}

interface RouteHandler {
  match: (url: string, method: string) => boolean;
  status?: number;
  body: () => unknown;
}

/** Stub global fetch with route predicates so tests never touch the network. */
function installFetch(handlers: RouteHandler[]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    for (const handler of handlers) {
      if (handler.match(url, method)) {
        return jsonResponse(handler.status ?? 200, handler.body());
      }
    }
    throw new Error(`Unexpected fetch: ${method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderDashboard() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>
  );
}

const isActiveEndpoint = (url: string, method: string) =>
  url.includes("/api/analysis/active") && method === "GET";
const isJobEndpoint = (url: string, method: string) =>
  url.includes("/api/analysis/jobs/") && method === "GET";
const isSummaryEndpoint = (url: string, method: string) =>
  url.includes("/api/mailbox/summary") && method === "GET";
const isStartEndpoint = (url: string, method: string) =>
  url.includes("/api/analysis/start") && method === "POST";

describe("DashboardPage analysis state", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("restores a backend-active analysis after mount and shows progress", async () => {
    const running = { ...QUEUED_JOB, status: "RUNNING", messages_total: 10, messages_processed: 2 };
    installFetch([
      { match: isActiveEndpoint, body: () => ({ active: running }) },
      { match: isJobEndpoint, body: () => running },
      { match: isSummaryEndpoint, body: () => WITHOUT_SUMMARY },
    ]);

    renderDashboard();

    // The backend is the source of truth: no local job id was passed, yet the
    // active job is picked up and polled automatically after mount.
    await screen.findByText("Analysis in progress");
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("renders a safe failure state when the polled job fails", async () => {
    const failed = {
      ...QUEUED_JOB,
      status: "FAILED",
      error_code: "ExternalServiceError",
      error_message: "Gmail is not connected (or the grant was lost). Reconnect the account.",
    };
    installFetch([
      { match: isActiveEndpoint, body: () => ({ active: QUEUED_JOB }) },
      { match: isJobEndpoint, body: () => failed },
      { match: isSummaryEndpoint, body: () => WITHOUT_SUMMARY },
    ]);

    renderDashboard();

    await screen.findByText("Analysis failed");
    expect(
      screen.getByText(/Gmail is not connected \(or the grant was lost\)/)
    ).toBeInTheDocument();
  });
it("shows the empty state when nothing exists yet", async () => {
    installFetch([
      { match: isActiveEndpoint, body: () => ({ active: null }) },
      { match: isSummaryEndpoint, body: () => WITHOUT_SUMMARY },
    ]);

    renderDashboard();

    await screen.findByText("No analysis yet");
    expect(screen.getByRole("button", { name: "Start analysis" })).toBeInTheDocument();
  });

  it("resumes polling when start returns 409 instead of failing", async () => {
    let activeBody: unknown = { active: null };
    const running = { ...QUEUED_JOB, status: "RUNNING", messages_total: 10, messages_processed: 3 };
    installFetch([
      { match: isActiveEndpoint, body: () => ({ active: activeBody }) },
      { match: isJobEndpoint, body: () => running },
      { match: isSummaryEndpoint, body: () => WITHOUT_SUMMARY },
      {
        match: isStartEndpoint,
        status: 409,
        body: () => ({
          error: {
            code: "conflict",
            message: `Analysis ${running.job_id} is already QUEUED. Poll it instead.`,
          },
          request_id: "r-1",
        }),
      },
    ]);

    renderDashboard();
    await screen.findByText("No analysis yet");

    // A job became active in the backend between mount and the click.
    activeBody = running;
    await userEvent.click(screen.getByRole("button", { name: "Run analysis" }));

    // The 409 is handled by resuming the active job - no generic failure banner,
    // no duplicate job, and the progress UI takes over.
    await screen.findByText("Analysis in progress");
    expect(screen.queryByText(/already QUEUED/)).toBeNull();
    await waitFor(() => expect(screen.getByText("Running")).toBeInTheDocument());
  });

  it("renders a cancelled state for cancelled jobs", async () => {
    const cancelled = { ...QUEUED_JOB, status: "CANCELLED" };
    installFetch([
      { match: isActiveEndpoint, body: () => ({ active: QUEUED_JOB }) },
      { match: isJobEndpoint, body: () => cancelled },
      { match: isSummaryEndpoint, body: () => WITHOUT_SUMMARY },
    ]);

    renderDashboard();

    await screen.findByText("Analysis cancelled");
  });
});