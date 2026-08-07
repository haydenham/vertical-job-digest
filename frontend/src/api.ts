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

// Everything about a posting that is NOT about a résumé. Split out for the public demo board
// (D-105): `PublicPostingRow` is exactly this and nothing more, mirroring `PublicPostingRow` in
// `app.py`, which deliberately does not declare the match fields.
export interface BasePostingRow {
  posting_id: number;
  company: string;
  title: string | null;
  location: string | null;
  // The server's normalized rendering of `location` (D-106) — full state name, country affix and
  // ZIP stripped, "; "-joined multi-site rows preserved. Null when the raw string is already in
  // that form or cannot be improved, in which case show `location` verbatim. Never normalize here:
  // `src/vja/location.py` owns the judgment, exactly like `comp_display`.
  location_display: string | null;
  apply_url: string | null;
  first_seen_at: string;
  source_updated_at: string | null;
  // Compensation (F2 Phase A, D-087). `comp_display` is the server's guarded annual-USD range —
  // present only when `comp_raw` corroborates the extracted integers as annual USD (see
  // `src/vja/comp.py`). When it is null, show `comp_raw` verbatim; never format the integers here.
  comp_min: number | null;
  comp_max: number | null;
  comp_raw: string | null;
  comp_display: string | null;
}

export interface PostingRow extends BasePostingRow {
  verdict: Verdict | null;
  score: number | null;
  fits: string[] | null;
  gaps: string[] | null;
  rationale: string | null;
  // Actionable advice (D-111). Null both for rows matched before the fields existed and for a role
  // the model had nothing honest to say about; the panel renders nothing in either case. These are
  // absent from `PublicPostingRow` by design — the demo board can never carry match text (D-105).
  resume_actions: string[] | null;
  application_notes: string[] | null;
}

// A row on the public demo board: the same posting, with no match data of any kind.
export type PublicPostingRow = BasePostingRow;

// What the shared table/panel components accept. Optional match fields rather than a union, so one
// component renders both boards and `locked` decides what it shows instead of a type guard at
// every reference.
export type DisplayPosting = BasePostingRow & Partial<Omit<PostingRow, keyof BasePostingRow>>;

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

// The authenticated identity (mirrors `MeUser` in `app.py`). `digest_paused` is the D-094
// email flag the settings page reads and flips via `PATCH /api/me`.
export interface User {
  email: string;
  name: string | null;
  digest_paused: boolean;
}

// Backfill progress as `/api/me` reports it (D-082): "running" while the signup/reupload
// catch-up computes (server-side staleness guard included), "done" once finished, null for
// profiles that never had a stamped backfill (pre-signal rows).
export type BackfillStatus = "running" | "done" | null;

// The user's one active profile (mirrors `MeProfile`); `null` in `Me` ⇒ signed in but not onboarded.
export interface Profile {
  vertical: string;
  resume_version: string;
  backfill_status: BackfillStatus;
}

// `GET /api/me` — the SPA's routing source of truth (D-064/D-065): who you are + your one vertical
// (or `profile: null` ⇒ send to onboarding, not a 404ing dashboard). `null` = not logged in (401).
export interface Me {
  user: User;
  profile: Profile | null;
}

// `POST /api/profiles` success body (mirrors `ProfileCreated` in `app.py`). The backfill it
// triggers runs in the background; `/api/me.profile.backfill_status` reports its progress (D-082).
export interface ProfileCreated {
  profile_id: number;
  vertical: string;
  resume_version: string;
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
async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, { credentials: "include", signal });
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

// ---- the public demo board (D-105) ----
//
// The login-free half of the app: same live data, no match text, no session. These are the only
// calls that send no credentials — a signed-in visitor's cookie has no business on a public route,
// and omitting it also keeps the responses cacheable by the edge.

export interface PublicPostingsResponse {
  vertical: string;
  window: Window;
  count: number;
  postings: PublicPostingRow[];
}

// One entry in the demo's vertical toggle. `count` is why this exists rather than reusing
// `/api/verticals`: a vertical with nothing open would open onto an empty table.
export interface PublicVertical {
  vertical: string;
  count: number;
}

async function getPublicJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, { credentials: "omit", signal });
  if (!resp.ok) {
    throw new ApiError(resp.status, `${resp.status} ${resp.statusText} for ${path}`);
  }
  return (await resp.json()) as T;
}

// No `view` param: without a résumé there is nothing to be matched against, so the public board is
// always the whole in-scope universe. Recency is the one axis that still means something.
export function publicPostingsPath(vertical: string, window: Window): string {
  const params = new URLSearchParams({ vertical, window });
  return `/api/public/postings?${params.toString()}`;
}

export function fetchPublicPostings(
  vertical: string,
  window: Window,
  signal?: AbortSignal,
): Promise<PublicPostingsResponse> {
  return getPublicJson<PublicPostingsResponse>(publicPostingsPath(vertical, window), signal);
}

export function fetchPublicVerticals(): Promise<PublicVertical[]> {
  return getPublicJson<PublicVertical[]>("/api/public/verticals");
}

export function fetchPublicPostingDescription(
  postingId: number,
  vertical: string,
  signal?: AbortSignal,
): Promise<PostingDetail> {
  return getPublicJson<PostingDetail>(
    `/api/public/postings/${postingId}?vertical=${encodeURIComponent(vertical)}`,
    signal,
  );
}

// ---- posting body (D-095) ----

// Mirrors `PostingDetailRow` in `app.py`. `description` is null for a posting whose body hasn't
// been captured yet (no backfill — rows fill as they insert, change, reopen, or re-extract).
export interface PostingDetail {
  posting_id: number;
  description: string | null;
}

export function postingDetailPath(postingId: number, vertical: string): string {
  return `/api/postings/${postingId}?vertical=${encodeURIComponent(vertical)}`;
}

// Fetched only when a detail panel opens — bodies run ~3 KB each, so they are deliberately not on
// the list response. `signal` lets a fast row-to-row click abandon the previous request.
export function fetchPostingDescription(
  postingId: number,
  vertical: string,
  signal?: AbortSignal,
): Promise<PostingDetail> {
  return getJson<PostingDetail>(postingDetailPath(postingId, vertical), signal);
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

// ---- settings (D-094 PR 3) ----

// `PATCH /api/me` response (mirrors `MeSettings` in `app.py`): the full settings state, including
// the fields this request did not touch, so the caller never has to guess what it now holds.
// `vertical` is null for a signed-in user with no profile.
export interface MeSettings {
  digest_paused: boolean;
  vertical: string | null;
}

// `PATCH /api/me` is a partial update: send only the fields that change. An empty body is a 422.
async function patchMe(body: Record<string, unknown>): Promise<MeSettings> {
  const resp = await fetch(`${API_BASE}/api/me`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await errorDetail(resp));
  }
  return (await resp.json()) as MeSettings;
}

// Pause/resume the digest email. Matching and the dashboard keep running server-side; only the
// email stops.
export function setDigestPaused(paused: boolean): Promise<MeSettings> {
  return patchMe({ digest_paused: paused });
}

// Self-serve vertical switch: re-files the user's *existing* résumé under `vertical` (no
// re-upload — the server already holds the résumé text) and starts a backfill. Typed failures:
// 409 nothing to switch yet, 429 the rolling window is still closed (`Retry-After` in seconds),
// 404 unknown vertical.
export function switchVertical(vertical: string): Promise<MeSettings> {
  return patchMe({ vertical });
}

// Hard account deletion (D-094): removes the user, their profile, matches, and digest history
// server-side in one transaction, and kills the session. 204 on success.
export async function deleteAccount(): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/me`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await errorDetail(resp));
  }
}

// ---- in-app feedback (D-100) ----

// One-to-one with `FeedbackCategory` in `src/vja/digest/feedback.py`; keep them in sync.
export type FeedbackCategory = "bug" | "idea" | "confusing" | "other";

// Max message length, mirroring `FEEDBACK_MAX_CHARS` server-side. The client enforces it so the
// user sees a counter instead of a 422; the server enforces it because clients lie.
export const FEEDBACK_MAX_CHARS = 5000;

// Send one report. Nothing is stored: the server emails it to the operator with the user's
// identity, vertical, and user agent attached server-side, so this body stays minimal. 202 on
// success; 502 (provider down) and 503 (mail unconfigured) are both retryable.
export async function sendFeedback(
  category: FeedbackCategory,
  message: string,
  page: string,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category, message, page }),
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await errorDetail(resp));
  }
}

// ---- résumé upload (the first write path, D-057) ----

// A hung upload must not leave the form on "Uploading…" forever — abort and let the user retry
// (a same-vertical retry is an idempotent update server-side, so aborting is always safe).
export const UPLOAD_TIMEOUT_MS = 30_000;

// The server's own résumé character cap (`vja.resume._MAX_CHARS`). Duplicated here so the paste
// box can count against it client-side; the server remains the one that enforces it (422).
export const RESUME_MAX_CHARS = 200_000;

// `POST /api/profiles` (multipart): send a résumé → create/update this user's profile → the
// server kicks off the signup backfill in the background and returns 202. `source` is the file
// the user chose **or** the text they pasted; the endpoint takes exactly one of the two, so this
// sends exactly one part and everything downstream is the same code path. Maps the server's guard
// responses to a typed `ApiError` (401 no session · 413 too large · 422 unreadable/empty résumé ·
// 429 daily LLM budget or reupload limit · 409 second vertical · 404 unknown vertical) carrying
// the server message for the form to show.
export async function uploadResume(
  vertical: string,
  source: File | string,
): Promise<ProfileCreated> {
  const form = new FormData();
  form.set("vertical", vertical);
  if (typeof source === "string") {
    form.set("resume_text", source);
  } else {
    form.set("file", source);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS);
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/api/profiles`, {
      method: "POST",
      credentials: "include",
      body: form,
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
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
