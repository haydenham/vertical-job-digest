import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { PostingRow } from "../api";
import { PostingsTable } from "./PostingsTable";

function row(over: Partial<PostingRow> = {}): PostingRow {
  return {
    posting_id: 1,
    company: "GridCo",
    title: "Grid Engineer",
    location: "Remote",
    apply_url: "https://example.com/apply",
    first_seen_at: "2026-06-20T00:00:00Z",
    source_updated_at: null,
    verdict: "yes",
    score: 72,
    fits: ["power markets"],
    gaps: ["no SCADA"],
    rationale: "Strong on dispatch optimization.",
    ...over,
  };
}

describe("PostingsTable", () => {
  it("renders a row with the apply link on the title", () => {
    render(<PostingsTable postings={[row()]} />);
    const link = screen.getByRole("link", { name: "Grid Engineer" });
    expect(link).toHaveAttribute("href", "https://example.com/apply");
    expect(screen.getByText("72")).toBeInTheDocument();
  });

  it("shows a dim em-dash, not a fake score, for an unassessed posting", () => {
    render(
      <PostingsTable postings={[row({ verdict: null, score: null, rationale: null })]} />,
    );
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("72")).not.toBeInTheDocument();
  });

  it("dims rejected (verdict=no) rows", () => {
    const { container } = render(<PostingsTable postings={[row({ verdict: "no" })]} />);
    expect(container.querySelector(".row.rejected")).toBeInTheDocument();
  });

  it("reveals fits / gaps / rationale only after the row is expanded", async () => {
    render(<PostingsTable postings={[row()]} />);
    expect(screen.queryByText("power markets")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Grid Engineer").closest(".row")!);
    expect(screen.getByText("power markets")).toBeInTheDocument();
    expect(screen.getByText("no SCADA")).toBeInTheDocument();
    expect(screen.getByText("Strong on dispatch optimization.")).toBeInTheDocument();
  });
});
