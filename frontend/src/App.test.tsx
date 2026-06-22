import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { fetchPostings, fetchVerticals, type PostingsResponse } from "./api";

vi.mock("./api", () => ({
  fetchVerticals: vi.fn(),
  fetchPostings: vi.fn(),
}));

const mockVerticals = vi.mocked(fetchVerticals);
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

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockVerticals.mockResolvedValue(["grid_power_software"]);
    mockPostings.mockResolvedValue(response());
  });

  it("resolves the vertical then renders the table", async () => {
    render(<App />);
    expect(await screen.findByText("Grid Engineer")).toBeInTheDocument();
    expect(mockPostings).toHaveBeenCalledWith(
      expect.objectContaining({ vertical: "grid_power_software", window: "all" }),
    );
  });

  it("refetches with the new window when a recency toggle is clicked", async () => {
    render(<App />);
    await screen.findByText("Grid Engineer");
    await userEvent.click(screen.getByRole("button", { name: "2 wk" }));
    await waitFor(() =>
      expect(mockPostings).toHaveBeenLastCalledWith(
        expect.objectContaining({ window: "two_weeks" }),
      ),
    );
  });

  it("shows the empty-state copy when no postings match", async () => {
    mockPostings.mockResolvedValue(response({ count: 0, postings: [] }));
    render(<App />);
    expect(await screen.findByText(/no postings match/i)).toBeInTheDocument();
  });

  it("surfaces an error when no active vertical exists", async () => {
    mockVerticals.mockResolvedValue([]);
    render(<App />);
    expect(await screen.findByText(/no active vertical/i)).toBeInTheDocument();
  });
});
