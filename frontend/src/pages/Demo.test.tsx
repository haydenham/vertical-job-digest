import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchPublicPostingDescription,
  fetchPublicPostings,
  fetchPublicVerticals,
  type PublicPostingRow,
  type PublicPostingsResponse,
} from "../api";
import { Demo } from "./Demo";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  fetchPublicPostings: vi.fn(),
  fetchPublicVerticals: vi.fn(),
  fetchPublicPostingDescription: vi.fn(),
}));

const mockPostings = vi.mocked(fetchPublicPostings);
const mockVerticals = vi.mocked(fetchPublicVerticals);
const mockDescription = vi.mocked(fetchPublicPostingDescription);

function row(over: Partial<PublicPostingRow> = {}): PublicPostingRow {
  return {
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
    location_display: null,
    ...over,
  };
}

function response(over: Partial<PublicPostingsResponse> = {}): PublicPostingsResponse {
  return {
    vertical: "grid_power_software",
    window: "all",
    count: 1,
    postings: [row()],
    ...over,
  };
}

// Rendered inside a router with a real `/login` route, so "does the sign-in offer actually go
// somewhere" is a navigation assertion rather than an href string.
function renderDemo(initial = "/demo") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/demo" element={<Demo />} />
        <Route path="/login" element={<div>login page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockVerticals.mockReset();
  mockPostings.mockReset();
  mockDescription.mockReset();
  mockVerticals.mockResolvedValue([
    { vertical: "grid_power_software", count: 251 },
    { vertical: "robotics_software", count: 88 },
  ]);
  mockPostings.mockResolvedValue(response());
  mockDescription.mockReturnValue(new Promise(() => undefined));
});

describe("Demo", () => {
  it("renders the real board for a visitor with no account", async () => {
    renderDemo();
    expect(await screen.findByRole("link", { name: "Grid Engineer" })).toHaveAttribute(
      "href",
      "https://example.com/apply",
    );
    expect(screen.getByText("1 open")).toBeInTheDocument();
  });

  it("opens on the fullest vertical when none is requested", async () => {
    renderDemo();
    await waitFor(() => expect(mockPostings).toHaveBeenCalledWith(
      "grid_power_software",
      "all",
      expect.any(AbortSignal),
    ));
  });

  it("honours ?vertical= so a single-vertical post can link straight at its own board", async () => {
    renderDemo("/demo?vertical=robotics_software");
    await waitFor(() => expect(mockPostings).toHaveBeenCalledWith(
      "robotics_software",
      "all",
      expect.any(AbortSignal),
    ));
  });

  it("falls back to the fullest board when ?vertical= names one with nothing in it", async () => {
    renderDemo("/demo?vertical=vertical_that_was_retired");
    await waitFor(() => expect(mockPostings).toHaveBeenCalledWith(
      "grid_power_software",
      "all",
      expect.any(AbortSignal),
    ));
  });

  it("switches vertical from the toggle and refetches", async () => {
    renderDemo();
    await screen.findByRole("link", { name: "Grid Engineer" });

    await userEvent.click(screen.getByRole("button", { name: /robotics/i }));

    await waitFor(() => expect(mockPostings).toHaveBeenLastCalledWith(
      "robotics_software",
      "all",
      expect.any(AbortSignal),
    ));
  });

  it("keeps the recency toggle live — it needs no résumé", async () => {
    renderDemo();
    await screen.findByRole("link", { name: "Grid Engineer" });

    await userEvent.click(screen.getByRole("button", { name: "1 week" }));

    await waitFor(() => expect(mockPostings).toHaveBeenLastCalledWith(
      "grid_power_software",
      "week",
      expect.any(AbortSignal),
    ));
  });

  it("sends 'Matched for you' to sign-in instead of switching the view", async () => {
    renderDemo();
    await screen.findByRole("link", { name: "Grid Engineer" });

    await userEvent.click(screen.getByRole("button", { name: /matched for you/i }));

    expect(await screen.findByText("login page")).toBeInTheDocument();
  });

  it("locks the match column rather than dropping it", async () => {
    renderDemo();
    await screen.findByRole("link", { name: "Grid Engineer" });
    // The column header is still the dashboard's.
    expect(screen.getByRole("button", { name: /match/ })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /sign in/i }).length).toBeGreaterThan(0);
  });

  it("opens the detail panel with the sign-in offer in place of a rationale", async () => {
    mockDescription.mockResolvedValue({ posting_id: 1, description: "The full description." });
    renderDemo();
    await screen.findByRole("link", { name: "Grid Engineer" });

    await userEvent.click(screen.getByText("GridCo"));

    expect(await screen.findByText("The full description.")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /log in to view your matches/i }),
    ).toBeInTheDocument();
  });

  it("filters client-side without refetching", async () => {
    mockPostings.mockResolvedValue(
      response({
        count: 2,
        postings: [row(), row({ posting_id: 2, company: "Fluence", title: "Controls Engineer" })],
      }),
    );
    renderDemo();
    await screen.findByRole("link", { name: "Grid Engineer" });
    const callsBefore = mockPostings.mock.calls.length;

    await userEvent.type(screen.getByRole("searchbox"), "fluence");

    expect(await screen.findByText("1 of 2")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Grid Engineer" })).not.toBeInTheDocument();
    expect(mockPostings.mock.calls.length).toBe(callsBefore);
  });

  it("shows a readable failure rather than an empty page when the board can't load", async () => {
    mockVerticals.mockRejectedValue(new Error("network down"));
    renderDemo();
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't load the board/i);
  });
});
