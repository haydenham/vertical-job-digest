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

// The authenticated identity (mirrors `MeUser` in `app.py`).
export interface User {
  email: string;
  name: string | null;
}

// The user's one active profile (mirrors `MeProfile`); `null` in `Me` ⇒ signed in but not onboarded.
export interface Profile {
  vertical: string;
  resume_version: string;
}

// `GET /api/me` — the SPA's routing source of truth (D-064/D-065): who you are + your one vertical
// (or `profile: null` ⇒ send to onboarding, not a 404ing dashboard). `null` = not logged in (401).
export interface Me {
  user: User;
  profile: Profile | null;
}

// `POST /api/profiles` success body (mirrors `ProfileCreated` in `app.py`). The backfill it
// triggers runs in the background — there's no status to poll (D-057), hence the optimistic UX.
export interface ProfileCreated {
  profile_id: number;
  vertical: string;
  resume_version: number;
}

// Carries the HTTP status so callers (the upload form) can branch on 401/413/422/429.
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// Every call is credentialed so the signed-cookie session (D-055) rides along: logged-in users
// resolve to their own profile server-side; anonymous keeps the single-active default.
async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, { credentials: "include" });
  if (!resp.ok) {
    throw new ApiError(resp.status, `${resp.status} ${resp.statusText} for ${path}`);
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

// ---- auth ----

// The Google OAuth entry point. Must target the API origin (not the Vite dev origin), so it goes
// through `API_BASE`. A plain anchor/`location` assignment — the browser follows the 302 to Google.
export function loginUrl(): string {
  return `${API_BASE}/auth/login`;
}

// Session probe. `/api/me` returns 401 when unauthenticated — that's "logged out", not an error,
// so it resolves to `null` rather than throwing. On 200 it carries the user + their one profile.
export async function fetchMe(): Promise<Me | null> {
  const resp = await fetch(`${API_BASE}/api/me`, { credentials: "include" });
  if (resp.status === 401) return null;
  if (!resp.ok) {
    throw new ApiError(resp.status, `${resp.status} ${resp.statusText} for /api/me`);
  }
  return (await resp.json()) as Me;
}

export async function logout(): Promise<void> {
  const resp = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, `${resp.status} ${resp.statusText} for /auth/logout`);
  }
}

// ---- résumé upload (the first write path, D-057) ----

// `POST /api/profiles` (multipart): upload a résumé → create/update this user's profile → the
// server kicks off the signup backfill in the background and returns 202. Maps the server's
// guard responses to a typed `ApiError` (401 no session · 413 too large · 422 unreadable résumé ·
// 429 daily LLM budget · 404 unknown vertical) carrying the server message for the form to show.
export async function uploadResume(vertical: string, file: File): Promise<ProfileCreated> {
  const form = new FormData();
  form.set("vertical", vertical);
  form.set("file", file);
  const resp = await fetch(`${API_BASE}/api/profiles`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await errorDetail(resp));
  }
  return (await resp.json()) as ProfileCreated;
}

// FastAPI renders errors as `{"detail": "..."}`; surface that string, falling back to the status.
async function errorDetail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // non-JSON body — fall through
  }
  return `${resp.status} ${resp.statusText}`;
}
