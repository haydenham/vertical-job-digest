import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PostingRow } from "../api";
import { PostingPanel } from "./PostingPanel";

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

describe("PostingPanel", () => {
  it("renders title, company, meta, rationale, fits/gaps, and the apply link", () => {
    render(<PostingPanel p={row()} onClose={vi.fn()} />);
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
        <PostingPanel p={row()} onClose={onClose} />
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
    render(
      <PostingPanel
        p={row({ verdict: null, score: null, rationale: null, fits: null, gaps: null, apply_url: null })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("—")).toBeInTheDocument(); // unassessed match cell
    expect(screen.queryByText("fits")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  // --- salary (F2 Phase A, D-087) -------------------------------------------------------------

  it("shows the server's guarded range, with the posting's own wording beneath it", () => {
    render(
      <PostingPanel
        p={row({ comp_display: "$105,000 – $131,325", comp_raw: "$105,000 and $131,325/year" })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("salary")).toBeInTheDocument();
    expect(screen.getByText("$105,000 – $131,325")).toBeInTheDocument();
    expect(screen.getByText("$105,000 and $131,325/year")).toBeInTheDocument();
  });

  it("falls back to comp_raw verbatim when the server suppressed the range", () => {
    // The hourly-annualization case: the panel must never render a $ range the server withheld.
    render(
      <PostingPanel
        p={row({ comp_display: null, comp_raw: "$49.82 to $60.22 per hour" })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText("$49.82 to $60.22 per hour")).toBeInTheDocument();
  });

  it("says the salary is not listed rather than hiding the block", () => {
    render(<PostingPanel p={row({ comp_display: null, comp_raw: null })} onClose={vi.fn()} />);
    expect(screen.getByText("salary")).toBeInTheDocument();
    expect(screen.getByText("Not listed")).toBeInTheDocument();
  });

  it("does not repeat comp_raw when it is identical to the displayed range", () => {
    render(
      <PostingPanel
        p={row({ comp_display: "$120,000", comp_raw: "$120,000" })}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getAllByText("$120,000")).toHaveLength(1);
  });
});
