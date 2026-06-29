import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { ApiError, fetchVerticals, uploadResume, type ProfileCreated } from "../api";
import { useAuth } from "../auth/useAuth";

// Résumé upload (the first write path, D-057). Soft-guarded: no session → bounce to /login (the
// POST is hard-guarded by `require_user` server-side anyway). On 202 the backfill runs in the
// background with no status to poll, so the UI is optimistic + offers a manual refresh (the
// dashboard re-queries on navigation).
export function Upload() {
  const { user, loading } = useAuth();
  const [verticals, setVerticals] = useState<string[]>([]);
  const [vertical, setVertical] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState<ProfileCreated | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchVerticals()
      .then((vs) => {
        setVerticals(vs);
        if (vs.length > 0) setVertical(vs[0]);
      })
      .catch((e: unknown) => setError(String(e)));
  }, []);

  if (loading) return <div className="notice">loading…</div>;
  if (user === null) return <Navigate to="/login" replace />;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (file === null || vertical === "") return;
    setSubmitting(true);
    setError(null);
    setCreated(null);
    try {
      setCreated(await uploadResume(vertical, file));
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (created !== null) {
    return (
      <div className="panel">
        <p className="success-line">✓ résumé received (v{created.resume_version})</p>
        <p className="auth-blurb">
          Matching runs in the background — your matched roles appear over the next few minutes, and
          the full set after tonight&apos;s run.
        </p>
        <Link className="btn btn-primary" to="/">
          View dashboard
        </Link>
      </div>
    );
  }

  return (
    <form className="panel upload-form" onSubmit={onSubmit}>
      <label className="field">
        <span className="label">vertical</span>
        <select value={vertical} onChange={(e) => setVertical(e.target.value)}>
          {verticals.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span className="label">résumé (text, markdown, or text PDF)</span>
        <input
          type="file"
          accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>

      {error && <div className="notice error">// {error}</div>}

      <button className="btn btn-primary" type="submit" disabled={submitting || file === null}>
        {submitting ? "uploading…" : "upload résumé"}
      </button>
    </form>
  );
}
