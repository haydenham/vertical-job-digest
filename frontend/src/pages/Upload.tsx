import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError, fetchVerticals, uploadResume } from "../api";
import { useAuth } from "../auth/useAuth";
import { verticalCopy } from "../verticalCopy";

// Résumé upload — two modes (Phase B):
//   • onboarding (no `lockedVertical`): pick a vertical + upload; this is the new user's one-time
//     vertical choice (D-064).
//   • update (`lockedVertical` set): the vertical is fixed to theirs (immutable, one-vertical), only
//     the résumé changes.
// On success it refreshes `/api/me` (so a freshly-created profile lands before routing) then sends
// the user to their dashboard with `justOnboarded` so the matched view polls the backfill (D-065).

// Friendly leads for the write path's guard statuses (D-057; 409 = second vertical, D-064). The
// server detail still renders after the lead; unmapped statuses fall back to the detail alone.
const ERROR_LEADS: Record<number, string> = {
  409: "You're already set up in another vertical.",
  413: "That file is too large.",
  422: "That résumé couldn't be read as text.",
  429: "Today's matching budget is used up — try again tomorrow.",
};

interface FormError {
  lead: string | null;
  detail: string;
}

function toFormError(err: unknown): FormError {
  if (err instanceof ApiError) {
    return { lead: ERROR_LEADS[err.status] ?? null, detail: err.message };
  }
  return { lead: null, detail: String(err) };
}

function fileSize(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} KB`;
}

export function Upload({ lockedVertical }: { lockedVertical?: string } = {}) {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const [verticals, setVerticals] = useState<string[]>([]);
  const [picked, setPicked] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<FormError | null>(null);

  const isOnboarding = lockedVertical === undefined;

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
    if (file === null || vertical === "") return;
    setSubmitting(true);
    setError(null);
    try {
      await uploadResume(vertical, file);
      await refresh(); // pick up the new/updated profile before the dashboard routes on it
      navigate("/dashboard", { state: { justOnboarded: true } });
    } catch (err: unknown) {
      setError(toFormError(err));
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="panel auth-card upload-card" onSubmit={onSubmit}>
        <h1 className="auth-title">{isOnboarding ? "Set up your feed" : "Update your résumé"}</h1>
        <p className="auth-blurb">
          {isOnboarding
            ? "Pick your vertical and upload a résumé — we’ll match new roles to it nightly."
            : "Upload a new résumé; matching re-runs against it."}
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
              <span className="vertical-slug">{lockedVertical}</span>
            </div>
          </div>
        )}

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
            <span className="label">résumé</span>
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
              className="visually-hidden"
              accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>

        {error && (
          <div className="notice error form-error" role="alert">
            {error.lead && <strong className="error-lead">{error.lead}</strong>}
            <span className="error-detail">{error.detail}</span>
          </div>
        )}

        <button className="btn btn-primary" type="submit" disabled={submitting || file === null}>
          {submitting ? "Uploading…" : "Upload résumé"}
        </button>
      </form>
    </div>
  );
}
