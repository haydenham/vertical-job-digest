import { useEffect, useRef, useState } from "react";

import { ApiError, FEEDBACK_MAX_CHARS, type FeedbackCategory, sendFeedback } from "../api";

// In-app feedback (D-100): a dialog rather than a route, so reporting a bug never costs the user
// their place in the table. Nothing is stored server-side; the report is emailed to the operator
// with identity, vertical, and user agent attached there rather than collected here.
//
// A failed send keeps the typed text in state so Send is a real retry, and success swaps to a
// short acknowledgement instead of yanking the dialog away mid-thought.

const CATEGORIES: { value: FeedbackCategory; label: string; title: string }[] = [
  { value: "bug", label: "Bug", title: "Something is broken or wrong." },
  { value: "idea", label: "Idea", title: "Something you wish Rolefeed did." },
  { value: "confusing", label: "Confusing", title: "Something you could not figure out." },
  { value: "other", label: "Other", title: "Anything else." },
];

const PLACEHOLDERS: Record<FeedbackCategory, string> = {
  bug: "What happened, and what did you expect instead?",
  idea: "What would you like Rolefeed to do?",
  confusing: "What did you expect this to do?",
  other: "What is on your mind?",
};

function toErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof TypeError) {
    return "Couldn't reach the server. Check your connection and try again.";
  }
  return String(err);
}

export function FeedbackDialog({ page, onClose }: { page: string; onClose: () => void }) {
  const [category, setCategory] = useState<FeedbackCategory>("bug");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLElement>(null);

  // The Settings/WelcomeTour dialog pattern: focus on open, Escape closes, but never mid-send
  // (the buttons are disabled then too, so closing would strand a request the user can't see).
  useEffect(() => {
    dialogRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !sending) onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose, sending]);

  const trimmed = message.trim();
  const tooLong = message.length > FEEDBACK_MAX_CHARS;
  const canSend = trimmed.length > 0 && !tooLong && !sending;

  async function onSend() {
    if (!canSend) return;
    setSending(true);
    setError(null);
    try {
      await sendFeedback(category, trimmed, page);
      setSent(true);
    } catch (err: unknown) {
      setError(toErrorMessage(err));
    } finally {
      setSending(false);
    }
  }

  return (
    <div
      className="feedback-backdrop"
      data-testid="feedback-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !sending) onClose();
      }}
    >
      <section
        className="feedback-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="feedback-title"
        ref={dialogRef}
        tabIndex={-1}
      >
        {sent ? (
          <>
            <h2 id="feedback-title">Thank you</h2>
            <p className="feedback-hint">
              Your note is on its way. If it needs a reply, it will come to the email you signed in
              with.
            </p>
            <div className="feedback-actions">
              <button type="button" className="btn btn-primary" onClick={onClose}>
                Done
              </button>
            </div>
          </>
        ) : (
          <>
            <h2 id="feedback-title">Send feedback</h2>
            <p className="feedback-hint">
              Tell me what broke, what is confusing, or what you wish this did. It goes straight to
              the person building Rolefeed.
            </p>

            <div className="feedback-field">
              <span className="label">what kind</span>
              <div className="segmented" role="group" aria-label="feedback category">
                {CATEGORIES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    aria-pressed={category === item.value}
                    title={item.title}
                    disabled={sending}
                    onClick={() => setCategory(item.value)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="feedback-field">
              <label className="label" htmlFor="feedback-message">
                details
              </label>
              <textarea
                id="feedback-message"
                className="textarea"
                rows={6}
                value={message}
                disabled={sending}
                placeholder={PLACEHOLDERS[category]}
                onChange={(event) => setMessage(event.target.value)}
              />
              <div className="field-meta">
                <span>Your email and current page are included automatically.</span>
                {message.length > FEEDBACK_MAX_CHARS * 0.8 && (
                  <span className={tooLong ? "char-count over" : "char-count"}>
                    {message.length} / {FEEDBACK_MAX_CHARS}
                  </span>
                )}
              </div>
            </div>

            {error && (
              <div className="notice error" role="alert">
                {error}
              </div>
            )}

            <div className="feedback-actions">
              <button type="button" className="btn" onClick={onClose} disabled={sending}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => void onSend()}
                disabled={!canSend}
              >
                {sending ? "Sending…" : "Send"}
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
