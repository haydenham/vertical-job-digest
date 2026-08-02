import { type ReactNode, useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError, deleteAccount, fetchVerticals, setDigestPaused, switchVertical } from "../api";
import { useAuth } from "../auth/useAuth";
import { verticalCopy } from "../verticalCopy";

// Settings (D-094 PR 3): the digest pause/resume toggle, the vertical switch, and hard account
// deletion. Login-gated only — a signed-in user with no profile yet must still be able to delete
// their account, so there is no onboarding bounce here (unlike /upload).
//
// The toggle renders from `user.digest_paused` (context truth), so a failed PATCH "reverts" by
// never having moved; the silent `/api/me` refresh after a successful flip re-syncs it. Deletion
// is a two-step confirm modal (calm consequence copy, no type-to-confirm ceremony); on success
// the server has already killed the session, so we clear local auth state and land on the
// logged-out Landing.
//
// The vertical switch is the self-serve replacement for what used to be a support action. It is
// confirmed rather than immediate because it restarts matching, and it is hidden entirely for a
// user with no profile (there is nothing to switch, and the server 409s that case).

function toErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof TypeError) {
    return "Couldn't reach the server. Check your connection and try again.";
  }
  return String(err);
}

// Shared scaffold for both confirm modals: focus on open, Escape closes, backdrop click closes,
// and neither is possible while the action is in flight (both buttons are disabled then too).
function ConfirmDialog({
  testId,
  titleId,
  title,
  busy,
  confirmLabel,
  busyLabel,
  danger,
  error,
  onCancel,
  onConfirm,
  children,
}: {
  testId: string;
  titleId: string;
  title: string;
  busy: boolean;
  confirmLabel: string;
  busyLabel: string;
  danger?: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
  children: ReactNode;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  // Held in a ref so an inline arrow from the parent can't re-subscribe the listener every render.
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;

  useEffect(() => {
    dialogRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) cancelRef.current();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [busy]);

  return (
    <div
      className="settings-backdrop"
      data-testid={testId}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <section
        className="settings-confirm"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialogRef}
        tabIndex={-1}
      >
        <h2 id={titleId}>{title}</h2>
        {children}
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        <div className="settings-confirm-actions">
          <button type="button" className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className={danger ? "btn btn-danger" : "btn btn-primary"}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? busyLabel : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

export function Settings() {
  const { user, profile, loading, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const [digestBusy, setDigestBusy] = useState(false);
  const [digestError, setDigestError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [verticals, setVerticals] = useState<string[]>([]);
  const [pendingVertical, setPendingVertical] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);

  // The joinable list is config-driven server-side, so it is the right source for "what could I
  // switch to". A failed load simply leaves the section unrendered rather than showing a broken
  // control; the rest of the page keeps working.
  useEffect(() => {
    if (profile === null) return;
    let live = true;
    fetchVerticals()
      .then((list) => {
        if (live) setVerticals(list);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [profile]);

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

  async function onConfirmSwitch() {
    if (switching || pendingVertical === null) return;
    setSwitching(true);
    setSwitchError(null);
    try {
      await switchVertical(pendingVertical);
    } catch (err: unknown) {
      setSwitchError(toErrorMessage(err));
      setSwitching(false);
      return;
    }
    // The backfill is already running server-side. Re-read /api/me so the dashboard opens with
    // the new vertical and its "matching in progress" banner rather than the old vertical's rows.
    await refresh({ silent: true }).catch(() => undefined);
    setPendingVertical(null);
    setSwitching(false);
    navigate("/dashboard", { replace: true });
  }

  const receiving = user !== null && !user.digest_paused;
  const current = profile?.vertical ?? null;

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

      {/* Hidden entirely without a profile: there is nothing to switch, and the server 409s it. */}
      {current !== null && verticals.length > 0 && (
        <section className="panel settings-section">
          <h2>Your vertical</h2>
          <p className="settings-hint">
            Rolefeed follows one vertical at a time. Switching keeps your résumé and reads it
            against the new vertical, which usually takes 5 to 20 minutes. Your matches in{" "}
            {verticalCopy(current).name} are kept, so switching back later is quick.
          </p>
          <div className="segmented" role="group" aria-label="vertical">
            {verticals.map((v) => (
              <button
                key={v}
                type="button"
                aria-pressed={v === current}
                disabled={switching}
                onClick={() => {
                  if (v !== current) {
                    setSwitchError(null);
                    setPendingVertical(v);
                  }
                }}
              >
                {verticalCopy(v).name}
              </button>
            ))}
          </div>
          {switchError && !pendingVertical && (
            <div className="notice error" role="alert">
              {switchError}
            </div>
          )}
        </section>
      )}

      <section className="panel settings-section settings-danger">
        <h2>Delete account</h2>
        <p className="settings-hint">
          Permanently remove your account, résumé profile, matches, and digest history.
        </p>
        <button type="button" className="btn btn-danger" onClick={() => setConfirmOpen(true)}>
          Delete my account…
        </button>
      </section>

      {pendingVertical !== null && (
        <ConfirmDialog
          testId="switch-confirm-backdrop"
          titleId="switch-confirm-title"
          title={`Switch to ${verticalCopy(pendingVertical).name}?`}
          busy={switching}
          confirmLabel="Switch vertical"
          busyLabel="Switching…"
          error={switchError}
          onCancel={() => setPendingVertical(null)}
          onConfirm={() => void onConfirmSwitch()}
        >
          <p>
            Your résumé stays as it is. We&rsquo;ll read it against{" "}
            {verticalCopy(pendingVertical).name} roles, which usually takes 5 to 20 minutes, and
            your daily digest will come from that vertical instead. Nothing in{" "}
            {verticalCopy(current ?? "").name} is deleted, so you can switch back.
          </p>
        </ConfirmDialog>
      )}

      {confirmOpen && (
        <ConfirmDialog
          testId="delete-confirm-backdrop"
          titleId="delete-confirm-title"
          title="Delete your account?"
          busy={deleting}
          confirmLabel="Delete my account"
          busyLabel="Deleting…"
          danger
          error={deleteError}
          onCancel={() => setConfirmOpen(false)}
          onConfirm={() => void onConfirmDelete()}
        >
          <p>
            This permanently removes your account, résumé profile, matches, and digest history. It
            can&rsquo;t be undone. To come back, you&rsquo;d sign up again from scratch.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
