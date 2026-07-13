import { describe, expect, it } from "vitest";

import type { PostingRow } from "./api";
import { DEFAULT_SORT, activityIso, filterPostings, sortPostings } from "./postingsView";

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

describe("activityIso", () => {
  it("prefers the ATS date, falling back to first_seen_at", () => {
    expect(activityIso(row({ source_updated_at: "2026-07-01T00:00:00Z" }))).toBe(
      "2026-07-01T00:00:00Z",
    );
    expect(activityIso(row({ source_updated_at: null }))).toBe("2026-06-20T00:00:00Z");
  });
});

describe("sortPostings", () => {
  const a = row({ posting_id: 1, company: "alpha", score: 40, first_seen_at: "2026-06-01T00:00:00Z" });
  const b = row({ posting_id: 2, company: "Bravo", score: 90, first_seen_at: "2026-06-10T00:00:00Z" });
  const c = row({ posting_id: 3, company: "charlie", score: null, first_seen_at: "2026-06-05T00:00:00Z" });

  it("default sort is activity-desc — the server's freshness order", () => {
    expect(sortPostings([a, c, b], DEFAULT_SORT).map((p) => p.posting_id)).toEqual([2, 3, 1]);
  });

  it("sorts text keys case-insensitively and flips with direction", () => {
    expect(sortPostings([c, b, a], { key: "company", dir: "asc" }).map((p) => p.company)).toEqual(
      ["alpha", "Bravo", "charlie"],
    );
    expect(sortPostings([a, b, c], { key: "company", dir: "desc" }).map((p) => p.company)).toEqual(
      ["charlie", "Bravo", "alpha"],
    );
  });

  it("sorts score numerically with nulls last in BOTH directions", () => {
    expect(sortPostings([c, a, b], { key: "score", dir: "desc" }).map((p) => p.score)).toEqual([
      90, 40, null,
    ]);
    expect(sortPostings([c, a, b], { key: "score", dir: "asc" }).map((p) => p.score)).toEqual([
      40, 90, null,
    ]);
  });

  it("does not mutate the input array", () => {
    const input = [b, a];
    sortPostings(input, { key: "company", dir: "asc" });
    expect(input.map((p) => p.posting_id)).toEqual([2, 1]);
  });
});

describe("filterPostings", () => {
  const rows = [
    row({ posting_id: 1, company: "FlightAware", title: "Backend Engineer", location: "Austin, TX" }),
    row({ posting_id: 2, company: "Fluence", title: "Data Engineer", location: "Remote" }),
    row({ posting_id: 3, company: "Boeing", title: null, location: null }),
  ];

  it("matches case-insensitive substrings across company, title, and location", () => {
    expect(filterPostings(rows, "flight").map((p) => p.posting_id)).toEqual([1]);
    expect(filterPostings(rows, "ENGINEER").map((p) => p.posting_id)).toEqual([1, 2]);
    expect(filterPostings(rows, "remote").map((p) => p.posting_id)).toEqual([2]);
  });

  it("keeps everything on a blank or whitespace query, and handles null fields", () => {
    expect(filterPostings(rows, "")).toHaveLength(3);
    expect(filterPostings(rows, "   ")).toHaveLength(3);
    expect(filterPostings(rows, "boeing").map((p) => p.posting_id)).toEqual([3]);
  });
});
