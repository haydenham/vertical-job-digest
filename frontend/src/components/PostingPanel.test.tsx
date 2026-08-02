import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchPostingDescription,
  fetchPublicPostingDescription,
  type PostingDetail,
  type PostingRow,
} from "../api";
import { PostingPanel } from "./PostingPanel";

// The body is a per-open fetch (D-095), so every panel render hits this. Default: no stored body,
// which is also the state most rows are in until the corpus fills. The public twin (D-105) is
// stubbed alongside it so the locked tests can assert which of the two was called.
vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  fetchPostingDescription: vi.fn(),
  fetchPublicPostingDescription: vi.fn(),
}));

const mockFetch = vi.mocked(fetchPostingDescription);
const mockPublicFetch = vi.mocked(fetchPublicPostingDescription);

function detail(description: string | null): PostingDetail {
  return { posting_id: 1, description };
}

function row(over: Partial<PostingRow> = {}): PostingRow {
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
    verdict: "yes",
    score: 72,
    fits: ["power markets"],
    gaps: ["no SCADA"],
    rationale: "Strong on dispatch optimization.",
    ...over,
  };
}

function renderPanel(p: PostingRow = row(), onClose: () => void = vi.fn()) {
  return render(<PostingPanel p={p} vertical="energy_software" onClose={onClose} />);
}

beforeEach(() => {
  mockFetch.mockReset();
  // Default: a request that never settles. The panel's other content renders regardless, and no
  // late state update lands after a test that isn't about the body has finished.
  mockFetch.mockReturnValue(new Promise<PostingDetail>(() => undefined));
  mockPublicFetch.mockReset();
  mockPublicFetch.mockReturnValue(new Promise<PostingDetail>(() => undefined));
});

describe("PostingPanel", () => {
  it("renders title, company, meta, rationale, fits/gaps, and the apply link", () => {
    renderPanel();
    expect(screen.getByRole("dialog", { name: "Grid Engineer" })).toBeInTheDocument();
    expect(screen.getByText("GridCo")).toBeInTheDocument();
    expect(screen.getByText("Remote")).toBeInTheDocument();
    const shownDate = new Date("2026-06-20T00:00:00Z").toLocaleDateString("en-CA");
    expect(screen.getByText(shownDate)).toBeInTheDocument();
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByText("Strong on dispatch optimization.")).toBeInTheDocument();
    expect(screen.getByText("power markets")).toBeInTheDocument();
    expect(screen.getByText("no SCADA")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "apply ↗" })).toHaveAttribute(
      "href",
      "https://example.com/apply",
    );
  });

  it("closes on Escape, the ✕ button, and a click outside — but not a click inside", async () => {
    const onClose = vi.fn();
    render(
      <div>
        <span>outside</span>
        <PostingPanel p={row()} vertical="energy_software" onClose={onClose} />
      </div>,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.mouseDown(screen.getByText("outside"));
    expect(onClose).toHaveBeenCalledTimes(2);

    fireEvent.mouseDown(screen.getByText("Strong on dispatch optimization."));
    expect(onClose).toHaveBeenCalledTimes(2);

    await userEvent.click(screen.getByRole("button", { name: "Close details" }));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("omits rationale/fits-gaps/apply when absent (unassessed posting)", () => {
    renderPanel(
      row({
        verdict: null,
        score: null,
        rationale: null,
        fits: null,
        gaps: null,
        apply_url: null,
      }),
    );
    expect(screen.getByText("—")).toBeInTheDocument(); // unassessed match cell
    expect(screen.queryByText("fits")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  // --- salary (F2 Phase A, D-087) -------------------------------------------------------------

  it("shows the server's guarded range, with the posting's own wording beneath it", () => {
    renderPanel(row({ comp_display: "$105,000 – $131,325", comp_raw: "$105,000 and $131,325/year" }));
    expect(screen.getByText("salary")).toBeInTheDocument();
    expect(screen.getByText("$105,000 – $131,325")).toBeInTheDocument();
    expect(screen.getByText("$105,000 and $131,325/year")).toBeInTheDocument();
  });

  it("falls back to comp_raw verbatim when the server suppressed the range", () => {
    // The hourly-annualization case: the panel must never render a $ range the server withheld.
    renderPanel(row({ comp_display: null, comp_raw: "$49.82 to $60.22 per hour" }));
    expect(screen.getByText("$49.82 to $60.22 per hour")).toBeInTheDocument();
  });

  it("says the salary is not listed rather than hiding the block", () => {
    renderPanel(row({ comp_display: null, comp_raw: null }));
    expect(screen.getByText("salary")).toBeInTheDocument();
    expect(screen.getByText("Not listed")).toBeInTheDocument();
  });

  it("does not repeat comp_raw when it is identical to the displayed range", () => {
    renderPanel(row({ comp_display: "$120,000", comp_raw: "$120,000" }));
    expect(screen.getAllByText("$120,000")).toHaveLength(1);
  });

  // --- description (D-095 PR 2) ----------------------------------------------------------------

  it("fetches the body for the open posting and renders it", async () => {
    mockFetch.mockResolvedValue(detail("About the role\n\n- Python\n- SQL"));
    renderPanel();

    expect(mockFetch).toHaveBeenCalledWith(1, "energy_software", expect.any(AbortSignal));
    expect(await screen.findByText("description")).toBeInTheDocument();
    // Line structure is the only structure plain text has left, so it must survive to the DOM.
    expect(await screen.findByText(/About the role/)).toHaveTextContent("- Python");
  });

  it("renders nothing in the description slot while the body is still in flight", () => {
    // Regression (found in the D-095 live smoke): the loading state was the string "loading", and
    // the render check was `typeof description === "string"` — so mid-fetch the panel printed the
    // word "loading" to the user. The loading state must not be a string.
    renderPanel(); // default mock never settles
    expect(screen.queryByText("description")).not.toBeInTheDocument();
    expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
  });

  it("renders no description block when the posting has no stored body", async () => {
    mockFetch.mockResolvedValue(detail(null));
    renderPanel();
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(screen.queryByText("description")).not.toBeInTheDocument();
  });

  it("stays silent when the body request fails — the rest of the panel still stands", async () => {
    mockFetch.mockRejectedValue(new Error("network"));
    renderPanel();
    await waitFor(() => expect(mockFetch).toHaveBeenCalled());
    expect(screen.queryByText("description")).not.toBeInTheDocument();
    expect(screen.getByText("Strong on dispatch optimization.")).toBeInTheDocument();
  });

  it("refetches and aborts the previous request when the panel switches postings", async () => {
    mockFetch.mockResolvedValue(detail("First body"));
    const { rerender } = renderPanel();
    expect(await screen.findByText("First body")).toBeInTheDocument();
    const firstSignal = mockFetch.mock.calls[0][2];

    mockFetch.mockResolvedValue(detail("Second body"));
    rerender(
      <PostingPanel p={row({ posting_id: 2 })} vertical="energy_software" onClose={vi.fn()} />,
    );

    expect(await screen.findByText("Second body")).toBeInTheDocument();
    expect(firstSignal?.aborted).toBe(true); // the stale body can't land in the new panel
    expect(mockFetch).toHaveBeenLastCalledWith(2, "energy_software", expect.any(AbortSignal));
  });

  // --- the public demo board (D-105) -----------------------------------------------------------

  describe("locked", () => {
    function renderLocked(p: PostingRow = row()) {
      return render(
        <MemoryRouter>
          <PostingPanel p={p} vertical="energy_software" locked onClose={vi.fn()} />
        </MemoryRouter>,
      );
    }

    it("offers sign-in in the match slot rather than a verdict", () => {
      renderLocked();
      const cta = screen.getByRole("link", { name: /log in to view your matches/i });
      expect(cta).toHaveAttribute("href", "/login");
      expect(screen.queryByText("72")).not.toBeInTheDocument();
    });

    it("shows no rationale, fits or gaps even when the row carries them", () => {
      // The row here is a full private one on purpose: the guarantee has to hold in this
      // component, not merely because the public API omits the fields.
      renderLocked();
      expect(screen.queryByText("Strong on dispatch optimization.")).not.toBeInTheDocument();
      expect(screen.queryByText("power markets")).not.toBeInTheDocument();
      expect(screen.queryByText("no SCADA")).not.toBeInTheDocument();
    });

    it("still shows the real posting: salary, location, body and apply link", async () => {
      mockPublicFetch.mockResolvedValue(detail("The full role description."));
      renderLocked(row({ comp_display: "$150,000 – $180,000" }));

      expect(await screen.findByText("The full role description.")).toBeInTheDocument();
      expect(screen.getByText("$150,000 – $180,000")).toBeInTheDocument();
      expect(screen.getByText("Remote")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /apply/i })).toHaveAttribute(
        "href",
        "https://example.com/apply",
      );
    });

    it("loads the body from the public endpoint, never the authenticated one", async () => {
      mockPublicFetch.mockResolvedValue(detail("Public body"));
      renderLocked();

      expect(await screen.findByText("Public body")).toBeInTheDocument();
      expect(mockPublicFetch).toHaveBeenCalledWith(
        1,
        "energy_software",
        expect.any(AbortSignal),
      );
      expect(mockFetch).not.toHaveBeenCalled();
    });
  });
});
