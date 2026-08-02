import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { PostingRow } from "../api";
import { DEFAULT_SORT } from "../postingsView";
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

function renderTable(
  postings: PostingRow[],
  over: Partial<React.ComponentProps<typeof PostingsTable>> = {},
) {
  const props = {
    postings,
    sort: DEFAULT_SORT,
    onSort: vi.fn(),
    selectedId: null,
    onSelect: vi.fn(),
    ...over,
  };
  return { ...render(<PostingsTable {...props} />), props };
}

describe("PostingsTable", () => {
  it("renders a row with the apply link on the title", () => {
    renderTable([row()]);
    const link = screen.getByRole("link", { name: "Grid Engineer" });
    expect(link).toHaveAttribute("href", "https://example.com/apply");
    expect(screen.getByText("72")).toBeInTheDocument();
  });

  it("shows a dim em-dash, not a fake score, for an unassessed posting", () => {
    renderTable([row({ verdict: null, score: null, rationale: null })]);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("72")).not.toBeInTheDocument();
  });

  it("dims rejected (verdict=no) rows", () => {
    const { container } = renderTable([row({ verdict: "no" })]);
    expect(container.querySelector(".row.rejected")).toBeInTheDocument();
  });

  it("shows the rationale snippet in the row, and omits it when unassessed", () => {
    const { container } = renderTable([
      row(),
      row({ posting_id: 2, title: "Ops Analyst", verdict: null, score: null, rationale: null }),
    ]);
    expect(screen.getByText("Strong on dispatch optimization.")).toBeInTheDocument();
    expect(container.querySelectorAll(".cell-snippet")).toHaveLength(1);
  });

  it("carries the verdict as a row spine class, and selection as .selected", () => {
    const { container } = renderTable(
      [row(), row({ posting_id: 2, verdict: "maybe", score: 51 })],
      { selectedId: 2 },
    );
    expect(container.querySelector(".row.v-yes")).toBeInTheDocument();
    expect(container.querySelector(".row.v-maybe.selected")).toBeInTheDocument();
  });

  it("row click reports the posting id for the side panel — no inline expansion", async () => {
    const { props } = renderTable([row()]);
    expect(screen.queryByText("power markets")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("GridCo").closest(".row")!);
    expect(props.onSelect).toHaveBeenCalledWith(1);
    expect(screen.queryByText("power markets")).not.toBeInTheDocument(); // panel is Dashboard's job
  });

  it("header click sorts by that column's natural direction, second click flips", async () => {
    const { props, unmount } = renderTable([row()]);
    await userEvent.click(screen.getByRole("button", { name: "company" }));
    expect(props.onSort).toHaveBeenCalledWith({ key: "company", dir: "asc" });
    unmount();

    const { props: sorted } = renderTable([row()], { sort: { key: "company", dir: "asc" } });
    await userEvent.click(screen.getByRole("button", { name: /company/ }));
    expect(sorted.onSort).toHaveBeenCalledWith({ key: "company", dir: "desc" });
  });

  it("marks the active sort column with aria-sort", () => {
    const { container } = renderTable([row()], { sort: { key: "score", dir: "desc" } });
    expect(container.querySelector('[aria-sort="descending"] .sort-btn.active')).toHaveTextContent(
      "match",
    );
  });

  // --- click affordance (D-087) ---------------------------------------------------------------

  it("marks each row with a decorative chevron that AT never reads", () => {
    const { container } = renderTable([row()]);
    const chevrons = container.querySelectorAll(".cell-chevron");
    expect(chevrons).toHaveLength(1);
    // The row already carries role="button" + aria-expanded — the glyph must not double it up.
    expect(chevrons[0]).toHaveAttribute("aria-hidden", "true");
  });

  it("marks the open row so the chevron can turn with it", () => {
    const { container } = renderTable([row()], { selectedId: 1 });
    expect(container.querySelector(".row.selected .cell-chevron")).not.toBeNull();
  });

  // --- the public demo board (D-105) -----------------------------------------------------------

  it("locked: keeps the match column but offers sign-in in place of a verdict", () => {
    renderLockedTable([row()]);
    const lock = screen.getByRole("link", { name: /sign in/i });
    expect(lock).toHaveAttribute("href", "/login");
    // The column header is still there — the demo is the dashboard, not a cut-down table.
    expect(screen.getByRole("button", { name: /match/ })).toBeInTheDocument();
  });

  it("locked: never renders a score or verdict, even if one somehow reaches the row", () => {
    // A public row carries no match fields at all; passing one that does is the belt-and-braces
    // check that this component, not just the API response, is what withholds them.
    renderLockedTable([row({ verdict: "strong_yes", score: 98 })]);
    expect(screen.queryByText("98")).not.toBeInTheDocument();
    expect(screen.queryByText("strong")).not.toBeInTheDocument();
  });

  it("locked: the match header does not sort, since every cell is the same lock", () => {
    const { props } = renderLockedTable([row()]);
    return userEvent.click(screen.getByRole("button", { name: /match/ })).then(() => {
      expect(props.onSort).not.toHaveBeenCalled();
    });
  });

  it("locked: clicking the lock does not also open the detail panel", async () => {
    const { props } = renderLockedTable([row()]);
    await userEvent.click(screen.getByRole("link", { name: /sign in/i }));
    expect(props.onSelect).not.toHaveBeenCalled();
  });
});

function renderLockedTable(postings: PostingRow[]) {
  const props = {
    postings,
    sort: DEFAULT_SORT,
    onSort: vi.fn(),
    selectedId: null,
    locked: true,
    onSelect: vi.fn(),
  };
  // The locked cell is a router `Link`, so this half of the suite needs a router around it.
  return {
    ...render(
      <MemoryRouter>
        <PostingsTable {...props} />
      </MemoryRouter>,
    ),
    props,
  };
}
