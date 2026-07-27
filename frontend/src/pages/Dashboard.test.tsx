import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchPostings, type BackfillStatus, type PostingsResponse } from "../api";
import { useAuth, type AuthState } from "../auth/useAuth";
import { Dashboard } from "./Dashboard";

// `fetchPostingDescription` is stubbed to never settle: the panel fires it on open (D-095), and
// these tests are about the dashboard's own behavior, not the body it loads.
vi.mock("../api", () => ({
  fetchPostings: vi.fn(),
  fetchPostingDescription: vi.fn(() => new Promise(() => undefined)),
}));
vi.mock("../auth/useAuth", () => ({ useAuth: vi.fn() }));

const mockPostings = vi.mocked(fetchPostings);
const mockUseAuth = vi.mocked(useAuth);

// The dashboard reads its backfill status (and the silent re-probe) from useAuth (D-082).
function auth(backfillStatus: BackfillStatus = null, over: Partial<AuthState> = {}): AuthState {
  return {
    user: { email: "a@b.co", name: "A", digest_paused: false },
    profile: {
      vertical: "grid_power_software",
      resume_version: "v1",
      backfill_status: backfillStatus,
    },
    loading: false,
    authError: false,
    refresh: vi.fn().mockResolvedValue(null),
    logout: vi.fn(),
    ...over,
  };
}

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
        comp_min: null,
        comp_max: null,
        comp_raw: null,
        comp_display: null,
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

const renderDashboard = () => render(<Dashboard vertical="grid_power_software" />);

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(auth());
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

  it("puts the table guidance above the results and renders a human vertical name", async () => {
    const { container } = render(<Dashboard vertical="aviation_software" />);
    expect(await screen.findByText("Grid Engineer")).toBeInTheDocument();
    expect(screen.getByText("Aviation Technology")).toBeInTheDocument();
    expect(screen.queryByText("aviation_software")).not.toBeInTheDocument();

    // Names what the panel holds — the affordance half of the salary work (D-087).
    const guide = screen.getByText(
      /click a row for salary, match rationale, and apply link · read-only · updates nightly/i,
    );
    const table = container.querySelector(".table");
    expect(table).not.toBeNull();
    expect(guide.compareDocumentPosition(table!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(container.querySelector("footer.footer")).not.toBeInTheDocument();
  });

  it("refetches with the new window when a recency toggle is clicked", async () => {
    renderDashboard();
    await screen.findByText("Grid Engineer");
    await userEvent.click(screen.getByRole("button", { name: "2 weeks" }));
    await waitFor(() =>
      expect(mockPostings).toHaveBeenLastCalledWith(
        expect.objectContaining({ window: "two_weeks" }),
      ),
    );
  });

  it("shows the plain empty-state when no backfill was ever stamped", async () => {
    mockPostings.mockResolvedValue(empty());
    renderDashboard();
    expect(await screen.findByText(/no postings match/i)).toBeInTheDocument();
  });

  // --- the status-driven backfill poll (D-082, supersedes the justOnboarded router-state poll) ---

  it("polls status + postings while the backfill runs, streaming matches in", async () => {
    vi.useFakeTimers();
    const refresh = vi.fn().mockResolvedValue(null);
    mockUseAuth.mockReturnValue(auth("running", { refresh }));
    mockPostings.mockResolvedValueOnce(empty()); // first paint: nothing computed yet
    mockPostings.mockResolvedValue(response()); // next poll: a match has landed
    renderDashboard();

    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText(/matching in progress/i)).toBeInTheDocument();
    expect(screen.getByText(/matches appear here as they’re computed/i)).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(10_000)); // one poll tick
    expect(screen.getByText("Grid Engineer")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalledWith({ silent: true }); // the status re-probe, route not blanked
  });

  it("shows the banner above existing rows while re-matching (the reupload case)", async () => {
    mockUseAuth.mockReturnValue(auth("running"));
    renderDashboard();
    expect(await screen.findByText("Grid Engineer")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/matching in progress/i);
  });

  it("no banner and no poll once the server reports done", async () => {
    vi.useFakeTimers();
    mockUseAuth.mockReturnValue(auth("done"));
    renderDashboard();
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.queryByText(/matching in progress/i)).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(30_000)); // three would-be ticks
    expect(mockPostings).toHaveBeenCalledTimes(1); // never refetched — no interval running
  });

  it("empty matched view after a finished backfill points at tonight's run", async () => {
    mockUseAuth.mockReturnValue(auth("done"));
    mockPostings.mockResolvedValue(empty());
    renderDashboard();
    expect(
      await screen.findByText(/no matches yet\. full results after tonight’s run/i),
    ).toBeInTheDocument();
  });

  it("a poll tick keeps the current view — no blanking to 'loading…' (D-082)", async () => {
    vi.useFakeTimers();
    mockUseAuth.mockReturnValue(auth("running"));
    mockPostings.mockResolvedValueOnce(empty()); // first paint: still empty
    mockPostings.mockImplementation(() => new Promise(() => {})); // next tick: fetch stays in flight
    renderDashboard();

    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText(/matches appear here as they’re computed/i)).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(10_000)); // poll tick → refetch pending
    expect(screen.getByText(/matches appear here as they’re computed/i)).toBeInTheDocument();
    expect(screen.queryByText("loading…")).not.toBeInTheDocument();
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
