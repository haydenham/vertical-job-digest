import { useEffect, useRef, useState } from "react";

export const TOUR_SEEN_KEY = "rolefeed.tour.seen";

const SLIDES = [
  {
    title: "Your Rolefeed, updated nightly",
    body:
      "Rolefeed watches a curated set of employers in your technology vertical. Each night it " +
      "finds new, updated, and closed roles, verifies every apply link, and sends new matches " +
      "to your inbox.",
  },
  {
    title: "Matched for you",
    body:
      "This view shows roles recommended for your current résumé. Every verdict explains what " +
      "fits, what is missing, and whether the role is worth your time, including an honest no.",
  },
  {
    title: "Explore every in-scope role",
    body:
      "All in-scope is the complete cleaned feed for your vertical, including roles that are " +
      "unassessed or not recommended. Use New today, 1 week, 2 weeks, or All open to control " +
      "how far back you look.",
  },
  {
    title: "Open details and keep your résumé current",
    body:
      "Click any row (the ▸ on the right) to see its salary, rationale, fits, gaps, and apply " +
      "link. When your résumé changes, recent roles re-match within minutes and the full refresh " +
      "completes with the next nightly run.",
  },
] as const;

export function WelcomeTour({ onDismiss }: { onDismiss: () => void }) {
  const [index, setIndex] = useState(0);
  const dialogRef = useRef<HTMLElement>(null);
  const slide = SLIDES[index];
  const last = index === SLIDES.length - 1;

  useEffect(() => {
    dialogRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onDismiss();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onDismiss]);

  return (
    <div
      className="tour-backdrop"
      data-testid="welcome-tour-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onDismiss();
      }}
    >
      <section
        className="welcome-tour"
        role="dialog"
        aria-modal="true"
        aria-labelledby="welcome-tour-title"
        ref={dialogRef}
        tabIndex={-1}
      >
        <div className="tour-progress" aria-label={`Step ${index + 1} of ${SLIDES.length}`}>
          <span>
            {index + 1} of {SLIDES.length}
          </span>
          <div className="tour-dots" aria-hidden="true">
            {SLIDES.map((item, itemIndex) => (
              <span className={itemIndex === index ? "active" : ""} key={item.title} />
            ))}
          </div>
        </div>

        <div className="tour-copy">
          <span className="label">welcome to rolefeed</span>
          <h2 id="welcome-tour-title">{slide.title}</h2>
          <p>{slide.body}</p>
        </div>

        <div className="tour-actions">
          <button type="button" className="btn tour-skip" onClick={onDismiss}>
            Skip
          </button>
          <div className="tour-step-actions">
            {index > 0 && (
              <button type="button" className="btn" onClick={() => setIndex((value) => value - 1)}>
                Back
              </button>
            )}
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => (last ? onDismiss() : setIndex((value) => value + 1))}
            >
              {last ? "Start exploring" : "Next"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
