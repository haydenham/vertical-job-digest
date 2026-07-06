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

  it("falls back to 'after tonight's run' when the poll times out", async () => {
    vi.useFakeTimers();
    mockPostings.mockResolvedValue(empty()); // never lands
    renderDashboard({ justOnboarded: true });

    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText(/finding your matches/i)).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(150_000)); // exhaust the bounded poll
    expect(screen.getByText(/full results after tonight/i)).toBeInTheDocument();
  });
});
