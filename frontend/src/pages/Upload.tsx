import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError, fetchVerticals, uploadResume } from "../api";
import { useAuth } from "../auth/useAuth";

// Résumé upload — two modes (Phase B):
//   • onboarding (no `lockedVertical`): pick a vertical + upload; this is the new user's one-time
//     vertical choice (D-064).
//   • update (`lockedVertical` set): the vertical is fixed to theirs (immutable, one-vertical), only
//     the résumé changes.
// On success it refreshes `/api/me` (so a freshly-created profile lands before routing) then sends
// the user to their dashboard with `justOnboarded` so the matched view polls the backfill (D-065).
export function Upload({ lockedVertical }: { lockedVertical?: string } = {}) {
  const { user, loading, refresh } = useAuth();
  const navigate = useNavigate();
  const [verticals, setVerticals] = useState<string[]>([]);
  const [picked, setPicked] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOnboarding = lockedVertical === undefined;

  // Only the onboarding picker needs the list of joinable verticals; update mode is locked.
  useEffect(() => {
    if (!isOnboarding) return;
    fetchVerticals()
      .then((vs) => {
        setVerticals(vs);
        if (vs.length > 0) setPicked(vs[0]);
      })
      .catch((e: unknown) => setError(String(e)));
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
      setError(err instanceof ApiError ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <form className="panel upload-form" onSubmit={onSubmit}>
      <p className="auth-blurb">
        {isOnboarding
          ? "Pick your vertical and upload a résumé — we’ll match new roles to it nightly."
          : "Upload a new résumé; matching re-runs against it."}
      </p>

      <label className="field">
        <span className="label">vertical</span>
        {isOnboarding ? (
          <select value={picked} onChange={(e) => setPicked(e.target.value)}>
            {verticals.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        ) : (
          <span className="accent">{lockedVertical}</span>
        )}
      </label>

      <label className="field">
        <span className="label">résumé (text, markdown, or text PDF)</span>
        <input
          type="file"
          accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>

      {error && <div className="notice error">{error}</div>}

      <button className="btn btn-primary" type="submit" disabled={submitting || file === null}>
        {submitting ? "uploading…" : "upload résumé"}
      </button>
    </form>
  );
}
