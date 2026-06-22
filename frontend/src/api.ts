// Typed client for the read-only dashboard API (FastAPI, Phase 6 · B1). The shapes here mirror
// `PostingRow` / `PostingsResponse` in `src/vja/api/app.py` — that Pydantic model is the source
// of truth; keep them in sync. Dev points at the Vite-proxied FastAPI origin (CORS); prod is
// same-origin (FastAPI serves dist/), so the default base is empty.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

// Recency toggle — one-to-one with the API's `window` enum (D-030).
export type Window = "new_today" | "week" | "two_weeks" | "all";

// Match-status view — one-to-one with the API's `view` enum (D-043). `matched` = relevant matches
// only; `cleaned` = the whole in-scope US-software universe. Rejected (`no`) is never shown either way.
export type View = "matched" | "cleaned";

// Match verdicts (matches `models.RELEVANT_VERDICTS` + the rejecting "no"). Order = strength.
export type Verdict = "strong_yes" | "yes" | "maybe" | "no";

export interface PostingRow {
  posting_id: number;
  company: string;
  title: string | null;
  location: string | null;
  apply_url: string | null;
  first_seen_at: string;
  source_updated_at: string | null;
  verdict: Verdict | null;
  score: number | null;
  fits: string[] | null;
  gaps: string[] | null;
  rationale: string | null;
}

export interface PostingsResponse {
  vertical: string;
  profile_id: number;
  window: Window;
  view: View;
  count: number;
  postings: PostingRow[];
}

export interface PostingsQuery {
  vertical: string;
  window: Window;
  view: View;
  profileId?: number;
}

class ApiError extends Error {}

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`);
  if (!resp.ok) {
    throw new ApiError(`${resp.status} ${resp.statusText} for ${path}`);
  }
  return (await resp.json()) as T;
}

// Build the `/api/postings` query string from UI state. The toggle → param mapping is the
// contract the dashboard rests on, so it lives in one place and is unit-tested.
export function postingsPath(q: PostingsQuery): string {
  const params = new URLSearchParams({
    vertical: q.vertical,
    window: q.window,
    view: q.view,
  });
  if (q.profileId !== undefined) {
    params.set("profile_id", String(q.profileId));
  }
  return `/api/postings?${params.toString()}`;
}

export function fetchPostings(q: PostingsQuery): Promise<PostingsResponse> {
  return getJson<PostingsResponse>(postingsPath(q));
}

export function fetchVerticals(): Promise<string[]> {
  return getJson<string[]>("/api/verticals");
}
