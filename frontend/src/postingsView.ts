import type { DisplayPosting } from "./api";

// Activity = the ATS posted/updated date if known, else when we first saw it — mirrors the API's
// COALESCE(source_updated_at, first_seen_at) (D-024/D-030). ISO strings compare lexically.
export function activityIso(p: DisplayPosting): string {
  return p.source_updated_at ?? p.first_seen_at;
}

export type SortKey = "company" | "title" | "location" | "activity" | "score";
export type SortDir = "asc" | "desc";

export interface SortState {
  key: SortKey;
  dir: SortDir;
}

// Freshness-desc — reproduces the server's own order, so the unsorted table looks unchanged.
export const DEFAULT_SORT: SortState = { key: "activity", dir: "desc" };

// The direction a column starts in when first clicked: text scans A→Z, dates/scores best-first.
export const NATURAL_DIR: Record<SortKey, SortDir> = {
  company: "asc",
  title: "asc",
  location: "asc",
  activity: "desc",
  score: "desc",
};

function sortValue(p: DisplayPosting, key: SortKey): string | number | null {
  switch (key) {
    case "company":
      return p.company.toLowerCase();
    case "title":
      return p.title?.toLowerCase() ?? null;
    case "location":
      return p.location?.toLowerCase() ?? null;
    case "activity":
      return activityIso(p);
    case "score":
      // Absent entirely on a public row (D-105), which sorts it exactly like an unscored one.
      return p.score ?? null;
  }
}

// Non-mutating sort; nulls (untitled, unknown location, unscored) sink to the bottom in BOTH
// directions — a missing value is never "best".
export function sortPostings<T extends DisplayPosting>(postings: T[], sort: SortState): T[] {
  const flip = sort.dir === "desc" ? -1 : 1;
  return [...postings].sort((a, b) => {
    const va = sortValue(a, sort.key);
    const vb = sortValue(b, sort.key);
    if (va === null && vb === null) return 0;
    if (va === null) return 1;
    if (vb === null) return -1;
    if (va < vb) return -1 * flip;
    if (va > vb) return 1 * flip;
    return 0;
  });
}

// Case-insensitive substring match over company/title/location; blank query keeps everything.
export function filterPostings<T extends DisplayPosting>(postings: T[], query: string): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return postings;
  return postings.filter((p) =>
    [p.company, p.title, p.location].some((f) => f?.toLowerCase().includes(q)),
  );
}
