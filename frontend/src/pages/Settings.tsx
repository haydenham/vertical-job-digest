import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError, deleteAccount, setDigestPaused } from "../api";
import { useAuth } from "../auth/useAuth";

// Settings (D-094 PR 3): the digest pause/resume toggle + hard account deletion. Login-gated
// only — a signed-in user with no profile yet must still be able to delete their account, so
// there is no onboarding bounce here (unlike /upload).
//
// The toggle renders from `user.digest_paused` (context truth), so a failed PATCH "reverts" by
// never having moved; the silent `/api/me` refresh after a successful flip re-syncs it. Deletion
// is a two-step confirm modal (calm consequence copy, no type-to-confirm ceremony); on success
// the server has already killed the session, so we clear local auth state and land on the
// logged-out Landing.

function toErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof TypeError) {
    return "Couldn't reach the server. Check your connection and try again.";
  }
  return String(err);
}

export function Settings() {
  const { user, loading, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const [digestBusy, setDigestBusy] = useState(false);
  const [digestError, setDigestError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLElement>(null);

  // Confirm-dialog a11y (the WelcomeTour pattern): focus on open, Escape closes — but never
  // mid-delete, when both buttons are disabled too.
  useEffect(() => {
    if (!confirmOpen) return;
    dialogRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setConfirmOpen((open) => (deleting ? open : false));
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [confirmOpen, deleting]);

  if (loading) return <div className="notice">loading…</div>;
  // `deleted` keeps the post-deletion render (user just flipped to null) off the /login bounce
  // while the navigate to Landing lands.
  if (user === null && !deleted) return <Navigate to="/login" replace />;

  async function onToggleDigest() {
    if (digestBusy || user === null) return;
    setDigestBusy(true);
    setDigestError(null);
    try {
      await setDigestPaused(!user.digest_paused);
      await refresh({ silent: true });
    } catch (err: unknown) {
      setDigestError(toErrorMessage(err));
    } finally {
      setDigestBusy(false);
    }
  }

  async function onConfirmDelete() {
    if (deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteAccount();
    } catch (err: unknown) {
      setDeleteError(toErrorMessage(err));
      setDeleting(false);
      return;
    }
    // The account (and server session) is gone; clear local auth state and land on Landing.
    // `logout` can't meaningfully fail here — the POST is a no-op on a dead session — but a
    // transport hiccup mustn't strand a deleted user on a dead page.
    setDeleted(true);
    await logout().catch(() => undefined);
    navigate("/", { replace: true });
  }

  const receiving = user !== null && !user.digest_paused;

  return (
    <div className="settings-page">
      {/* Points at the smart root, not /dashboard: this page is login-gated only, so a user who
          has not onboarded yet can reach it, and `/` is the one route that sends a profiled user,
          an unprofiled one, and a logged-out one each to the right place (D-065). */}
      <Link to="/" className="back-link">
        ← Back
      </Link>
      <h1 className="settings-title">Settings</h1>

      <section className="panel settings-section">
        <h2>Email digest</h2>
        <label className="settings-toggle">
          <input
            type="checkbox"
            role="switch"
            checked={receiving}
            disabled={digestBusy}
            onChange={() => void onToggleDigest()}
          />
          <span className="settings-toggle-label">Daily digest email</span>
        </label>
        <p className="settings-hint">
          {receiving
            ? "New matches land in your inbox after each nightly run."
            : "Digest emails are paused. Matching and your dashboard keep running. Turn the toggle back on to resume, and you'll pick up where the digest left off."}
        </p>
        {digestError && (
          <div className="notice error" role="alert">
            {digestError}
          </div>
        )}
      </section>

      <section className="panel settings-section settings-danger">
        <h2>Delete account</h2>
        <p className="settings-hint">
          Permanently remove your account, résumé profile, matches, and digest history.
        </p>
        <button type="button" className="btn btn-danger" onClick={() => setConfirmOpen(true)}>
          Delete my account…
        </button>
      </section>

      {confirmOpen && (
        <div
          className="settings-backdrop"
          data-testid="delete-confirm-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !deleting) setConfirmOpen(false);
          }}
        >
          <section
            className="settings-confirm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-confirm-title"
            ref={dialogRef}
            tabIndex={-1}
          >
            <h2 id="delete-confirm-title">Delete your account?</h2>
            <p>
              This permanently removes your account, résumé profile, matches, and digest history.
              It can&rsquo;t be undone. To come back, you&rsquo;d sign up again from scratch.
            </p>
            {deleteError && (
              <div className="notice error" role="alert">
                {deleteError}
              </div>
            )}
            <div className="settings-confirm-actions">
              <button
                type="button"
                className="btn"
                onClick={() => setConfirmOpen(false)}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => void onConfirmDelete()}
                disabled={deleting}
              >
                {deleting ? "Deleting…" : "Delete my account"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
