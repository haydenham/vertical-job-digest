import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchPostings, type PostingsResponse } from "../api";
import { Dashboard } from "./Dashboard";

vi.mock("../api", () => ({ fetchPostings: vi.fn() }));

const mockPostings = vi.mocked(fetchPostings);

function response(over: Partial<PostingsResponse> = {}): PostingsResponse {
  return {
    vertical: "grid_power_software",
    profile_id: 1,
    window: "all",
    view: "matched",
    count: 1,
    postings: [
      {
        posting_id: 1,
        company: "GridCo",
        title: "Grid Engineer",
        location: "Remote",
        apply_url: "https://example.com/apply",
        first_seen_at: "2026-06-20T00:00:00Z",
        source_updated_at: null,
        verdict: "yes",
        score: 72,
        fits: [],
        gaps: [],
        rationale: null,
      },
    ],
    ...over,
  };
}

const empty = () => response({ count: 0, postings: [] });

// Dashboard is now single-vertical (the user's own, passed by the route) and lives under a Router
// (it reads `location.state.justOnboarded`).
function renderDashboard(opts: { justOnboarded?: boolean } = {}) {
  const entries = opts.justOnboarded
    ? [{ pathname: "/dashboard", state: { justOnboarded: true } }]
    : ["/dashboard"];
  return render(
    <MemoryRouter initialEntries={entries}>
      <Dashboard vertical="grid_power_software" />
    </MemoryRouter>,
  );
}

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPostings.mockResolvedValue(response());
  });
  afterEach(() => vi.useRealTimers());

  it("renders the table for the given vertical (no vertical picker)", async () => {
    renderDashboard();
    expect(await screen.findByText("Grid Engineer")).toBeInTheDocument();
    expect(mockPostings).toHaveBeenCalledWith(
      expect.objectContaining({ vertical: "grid_power_software", window: "all" }),
    );
  });

  it("refetches with the new window when a recency toggle is clicked", async () => {
    renderDashboard();
    await screen.findByText("Grid Engineer");
    await userEvent.click(screen.getByRole("button", { name: "2 wk" }));
    await waitFor(() =>
      expect(mockPostings).toHaveBeenLastCalledWith(
        expect.objectContaining({ window: "two_weeks" }),
      ),
    );
  });

  it("shows the plain empty-state when not freshly onboarded", async () => {
    mockPostings.mockResolvedValue(empty());
    renderDashboard();
    expect(await screen.findByText(/no postings match/i)).toBeInTheDocument();
  });

  it("polls the matched view after onboarding until matches arrive", async () => {
    vi.useFakeTimers();
    mockPostings.mockResolvedValueOnce(empty()); // first paint: backfill hasn't landed
    mockPostings.mockResolvedValue(response()); // next poll: a match appears
    renderDashboard({ justOnboarded: true });

    await act(() => vi.advanceTimersByTimeAsync(0)); // flush the initial fetch
    expect(screen.getByText(/finding your matches/i)).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(10_000)); // one poll interval → refetch
    expect(screen.getByText("Grid Engineer")).toBeInTheDocument();
  });

  it("a poll tick keeps the current view — no blanking to 'loading…' (D-082)", async () => {
    vi.useFakeTimers();
    mockPostings.mockResolvedValueOnce(empty()); // first paint: still empty
    mockPostings.mockImplementation(() => new Promise(() => {})); // next tick: fetch stays in flight
    renderDashboard({ justOnboarded: true });

    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText(/finding your matches/i)).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(10_000)); // poll tick → refetch pending
    expect(screen.getByText(/finding your matches/i)).toBeInTheDocument();
    expect(screen.queryByText("loading…")).not.toBeInTheDocument();
  });

  it("falls back to 'after tonight's run' when the poll times out", async () => {
    vi.useFakeTimers();
    mockPostings.mockResolvedValue(empty()); // never lands
    renderDashboard({ justOnboarded: true });

    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText(/finding your matches/i)).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(150_000)); // exhaust the bounded poll
    expect(screen.getByText(/full results after tonight/i)).toBeInTheDocument();
  });

  it("filter-as-you-type narrows rows client-side and shows X of N — no refetch", async () => {
    const two = response({
      count: 2,
      postings: [
        response().postings[0],
        { ...response().postings[0], posting_id: 2, company: "FlightAware", title: "Ops Analyst" },
      ],
    });
    mockPostings.mockResolvedValue(two);
    renderDashboard();
    await screen.findByText("Grid Engineer");
    const calls = mockPostings.mock.calls.length;

    await userEvent.type(screen.getByRole("searchbox", { name: "Filter postings" }), "flight");
    expect(screen.getByText("Ops Analyst")).toBeInTheDocument();
    expect(screen.queryByText("Grid Engineer")).not.toBeInTheDocument();
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
    expect(mockPostings.mock.calls.length).toBe(calls);

    await userEvent.type(screen.getByRole("searchbox", { name: "Filter postings" }), "zzz");
    expect(screen.getByText(/no postings match “flightzzz”/i)).toBeInTheDocument();
  });

  it("row click opens the side panel; Esc closes it", async () => {
    mockPostings.mockResolvedValue(
      response({
        postings: [
          {
            ...response().postings[0],
            rationale: "Strong on dispatch optimization.",
            fits: ["power markets"],
            gaps: ["no SCADA"],
          },
        ],
      }),
    );
    renderDashboard();
    await screen.findByText("Grid Engineer");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("GridCo").closest(".row")!);
    const panel = await screen.findByRole("dialog", { name: "Grid Engineer" });
    expect(panel).toBeInTheDocument();
    expect(screen.getByText("power markets")).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
