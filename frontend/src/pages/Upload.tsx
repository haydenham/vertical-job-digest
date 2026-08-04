import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError, fetchVerticals, RESUME_MAX_CHARS, uploadResume } from "../api";
import { useAuth } from "../auth/useAuth";
import { verticalCopy } from "../verticalCopy";

// Résumé upload — two modes (Phase B):
//   • onboarding (no `lockedVertical`): pick a vertical + upload; this is the new user's one-time
//     vertical choice (D-064).
//   • update (`lockedVertical` set): the vertical is fixed to theirs (immutable, one-vertical), only
//     the résumé changes.
// On success it refreshes `/api/me` (so a freshly-created profile lands before routing) then sends
// the user to their dashboard with `justOnboarded` so the matched view polls the backfill (D-065).
//
// The 202 is the commit point (D-082): once the server accepts the résumé, nothing that happens
// after may present as an upload failure — the `/api/me` re-probe is silent (no global `loading`
// flip, so the form stays mounted) and retries bounded before falling back to a calm
// "uploaded — open your dashboard" state.
//
// Update 1.2 adds a second *input* mode: file or pasted text. It is deliberately only an input
// choice — one submit handler, one error surface, one commit point — because a résumé in a Google
// Doc or on a phone otherwise has to be exported to a file before the user can see a single job.

// Friendly leads for the write path's guard statuses (D-057; 409 = second vertical, D-064). The
// server detail still renders after the lead; unmapped statuses fall back to the detail alone.
const ERROR_LEADS: Record<number, string> = {
  409: "You're already set up in another vertical.",
  413: "That file is too large.",
  422: "That résumé couldn't be read as text.",
  429: "Today's matching budget is used up. Try again tomorrow.",
};

interface FormError {
  lead: string | null;
  detail: string;
}

function toFormError(err: unknown): FormError {
  if (err instanceof ApiError) {
    return { lead: ERROR_LEADS[err.status] ?? null, detail: err.message };
  }
  // Transport failures reach the user in words, not as a raw `TypeError: Failed to fetch`.
  if (err instanceof DOMException && err.name === "AbortError") {
    return { lead: "The upload timed out.", detail: "Check your connection and try again." };
  }
  if (err instanceof TypeError) {
    return { lead: "Couldn't reach the server.", detail: "Check your connection and try again." };
  }
  return { lead: null, detail: String(err) };
}

// idle → uploading (POST in flight) → finalizing (202 landed, re-probing /api/me) → navigate;
// "stalled" is the bounded-retry fallback: uploaded for sure, but the fresh profile never came
// back — offer a full-page hop to the dashboard (which re-probes auth from scratch).
type Phase = "idle" | "uploading" | "finalizing" | "stalled";

// Which input the user is filling in. Only one is submitted (the endpoint 422s on both).
type Mode = "file" | "text";

// Retry pacing for the post-202 profile probe (first attempt immediate).
const FINALIZE_DELAYS_MS = [0, 700, 1500, 3000];

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function fileSize(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} KB`;
}

export function Upload({ lockedVertical }: { lockedVertical?: string } = {}) {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const [verticals, setVerticals] = useState<string[]>([]);
  const [picked, setPicked] = useState("");
  const [mode, setMode] = useState<Mode>("file");
  const [file, setFile] = useState<File | null>(null);
  const [pasted, setPasted] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<FormError | null>(null);

  const isOnboarding = lockedVertical === undefined;
  const trimmed = pasted.trim();
  const tooLong = trimmed.length > RESUME_MAX_CHARS;
  // Exactly one input is submitted, so only the active mode decides whether there is anything
  // to send. Switching modes never discards what the other one holds.
  const source: File | string | null =
    mode === "file" ? file : trimmed !== "" && !tooLong ? trimmed : null;

  // Only the onboarding picker needs the list of joinable verticals; update mode is locked.
  useEffect(() => {
    if (!isOnboarding) return;
    fetchVerticals()
      .then((vs) => {
        setVerticals(vs);
        if (vs.length > 0) setPicked(vs[0]);
      })
      .catch((e: unknown) => setError(toFormError(e)));
  }, [isOnboarding]);

  if (loading) return <div className="notice">loading…</div>;
  if (user === null) return <Navigate to="/login" replace />;

  const vertical = lockedVertical ?? picked;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (source === null || vertical === "" || phase !== "idle") return;
    setPhase("uploading");
    setError(null);
    try {
      await uploadResume(vertical, source);
    } catch (err: unknown) {
      setError(toFormError(err));
      setPhase("idle");
      return;
    }
    // Commit point: the profile exists server-side. Pick it up (silently — the form must stay
    // mounted) before the dashboard routes on it; transient probe failures just mean try again.
    setPhase("finalizing");
    for (const delay of FINALIZE_DELAYS_MS) {
      if (delay > 0) await sleep(delay);
      try {
        const me = await refresh({ silent: true });
        if (me?.profile) {
          navigate("/dashboard", { state: { justOnboarded: true } });
          return;
        }
      } catch {
        // transient /api/me failure — retry on the next tick
      }
    }
    setPhase("stalled");
  }

  return (
    <div className="auth-page">
      <form className="panel auth-card upload-card" onSubmit={onSubmit}>
        {!isOnboarding && (
          <Link to="/dashboard" className="back-link">
            ← Back to dashboard
          </Link>
        )}
        <h1 className="auth-title">{isOnboarding ? "Set up your feed" : "Update your résumé"}</h1>
        <p className="auth-blurb">
          {isOnboarding
            ? "Pick your vertical and add your résumé, and we’ll match new roles to it every 4 hours."
            : "Add your updated résumé. Recent roles re-match within minutes, and your full refreshed results land after the next scheduled run."}
        </p>

        {isOnboarding ? (
          <fieldset className="vertical-picker">
            <legend className="label">vertical</legend>
            {verticals.map((v) => {
              const copy = verticalCopy(v);
              return (
                <label key={v} className={`vertical-card${picked === v ? " checked" : ""}`}>
                  <input
                    type="radio"
                    name="vertical"
                    value={v}
                    checked={picked === v}
                    onChange={() => setPicked(v)}
                    className="visually-hidden"
                  />
                  <span className="vertical-name">{copy.name}</span>
                  {copy.blurb && <span className="vertical-blurb">{copy.blurb}</span>}
                </label>
              );
            })}
          </fieldset>
        ) : (
          <div className="field">
            <span className="label">vertical</span>
            <div className="vertical-card locked">
              <span className="vertical-name">{verticalCopy(lockedVertical).name}</span>
            </div>
          </div>
        )}

        <div className="field">
          <span className="label">résumé</span>
          <div className="segmented" role="group" aria-label="résumé input">
            <button
              type="button"
              aria-pressed={mode === "file"}
              disabled={phase !== "idle"}
              onClick={() => setMode("file")}
            >
              Upload a file
            </button>
            <button
              type="button"
              aria-pressed={mode === "text"}
              disabled={phase !== "idle"}
              onClick={() => setMode("text")}
            >
              Paste text
            </button>
          </div>
        </div>

        {mode === "text" ? (
          <div className="field">
            <label className="visually-hidden" htmlFor="resume-text">
              résumé text
            </label>
            <textarea
              id="resume-text"
              className="textarea"
              rows={12}
              value={pasted}
              disabled={phase !== "idle"}
              placeholder="Paste your résumé here. Plain text is fine, formatting is not needed."
              onChange={(e) => setPasted(e.target.value)}
            />
            <div className="field-meta">
              <span>Copy it out of a doc, a PDF, or your LinkedIn profile.</span>
              <span className={tooLong ? "char-count over" : "char-count"}>
                {trimmed.length.toLocaleString()} / {RESUME_MAX_CHARS.toLocaleString()}
              </span>
            </div>
          </div>
        ) : (
          <div
            className={`dropzone${dragActive ? " drag-active" : ""}${file ? " has-file" : ""}`}
            onDragOver={(e) => {
              e.preventDefault(); // required for the drop event to fire
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragActive(false);
              const dropped = e.dataTransfer.files?.[0];
              if (dropped) setFile(dropped);
            }}
          >
            <label className="dropzone-label">
              {file ? (
                <>
                  <span className="file-name">{file.name}</span>
                  <span className="file-meta">{fileSize(file.size)} · choose a different file</span>
                </>
              ) : (
                <>
                  <span className="dropzone-cta">Drop your résumé here, or click to browse</span>
                  <span className="dropzone-hint">text, markdown, or text PDF</span>
                </>
              )}
              <input
                type="file"
                aria-label="résumé file"
                className="visually-hidden"
                accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>
        )}

        {error && (
          <div className="notice error form-error" role="alert">
            {error.lead && <strong className="error-lead">{error.lead}</strong>}
            <span className="error-detail">{error.detail}</span>
          </div>
        )}

        {phase === "uploading" && (
          <div className="notice busy" role="status">
            <span className="spinner" aria-hidden="true" />
            Uploading and starting your matches…
          </div>
        )}
        {phase === "finalizing" && (
          <div className="notice busy" role="status">
            <span className="spinner" aria-hidden="true" />
            Uploaded. Loading your dashboard…
          </div>
        )}
        {phase === "stalled" && (
          <div className="notice form-error" role="status">
            Your résumé is uploaded.{" "}
            <button
              type="button"
              className="link-button"
              onClick={() => window.location.assign("/dashboard")}
            >
              Open your dashboard
            </button>{" "}
            to continue.
          </div>
        )}

        <button
          className="btn btn-primary"
          type="submit"
          disabled={phase !== "idle" || source === null}
        >
          {phase === "uploading"
            ? "Uploading…"
            : phase === "idle"
              ? mode === "text"
                ? "Use this résumé"
                : "Upload résumé"
              : "Uploaded"}
        </button>

        <p className="upload-disclosure">
          By continuing, you agree your résumé is processed by AI models from Anthropic and OpenAI
          to generate your matches. See our <Link to="/privacy">privacy notice</Link>.
        </p>
      </form>
    </div>
  );
}
