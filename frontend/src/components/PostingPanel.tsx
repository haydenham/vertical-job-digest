import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  fetchPostingDescription,
  fetchPublicPostingDescription,
  type DisplayPosting,
} from "../api";
import { activityIso, displayLocation } from "../postingsView";
import { MatchCell } from "./Verdict";

// The posting body, loaded on open (D-095). `undefined` is "still loading" — deliberately NOT a
// string sentinel, which a `typeof === "string"` render check would happily print into the panel.
// `null` covers both "no stored body" and "the request failed"; either way nothing renders.
type Description = string | null | undefined;

// Overlay detail panel (PR 3, D-080): slides over the right side of the table — the table keeps
// full width underneath. Esc or a click outside closes; clicking another row closes on mousedown
// then re-selects on click, so the panel switches postings in place.
export function PostingPanel({
  p,
  vertical,
  locked = false,
  onClose,
}: {
  p: DisplayPosting;
  vertical: string;
  // The public demo board (D-105): the match slot offers sign-in instead of a rationale, and the
  // body comes from the public endpoint. Everything else in the panel is the real posting.
  locked?: boolean;
  onClose: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  const [description, setDescription] = useState<Description>(undefined);

  // The body is fetched per open rather than carried on the list response (~3 KB a row would cost
  // megabytes per dashboard load). Keyed on the posting id, so switching rows in place refetches;
  // the abort keeps a fast click-through from landing a stale body in the new panel.
  useEffect(() => {
    const controller = new AbortController();
    setDescription(undefined);
    const fetchBody = locked ? fetchPublicPostingDescription : fetchPostingDescription;
    fetchBody(p.posting_id, vertical, controller.signal)
      .then((detail) => setDescription(detail.description))
      // A missing body is not worth an error state — the panel's other content stands alone.
      .catch(() => {
        if (!controller.signal.aborted) setDescription(null);
      });
    return () => controller.abort();
  }, [p.posting_id, vertical, locked]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    function onMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onMouseDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [onClose]);

  return (
    <aside className="posting-panel" role="dialog" aria-label={p.title ?? "(untitled)"} ref={ref}>
      <header className="panel-head">
        <div>
          <h2 className="panel-title">{p.title ?? "(untitled)"}</h2>
          <span className="panel-company">{p.company}</span>
        </div>
        <button type="button" className="panel-close" onClick={onClose} aria-label="Close details">
          ✕
        </button>
      </header>

      <dl className="panel-meta">
        <div>
          <dt>match</dt>
          <dd>
            {locked ? (
              // Never a fabricated rationale — the offer to earn a real one (D-105).
              <Link to="/login" className="match-lock">
                Log in to view your matches
              </Link>
            ) : (
              <MatchCell verdict={p.verdict ?? null} score={p.score ?? null} />
            )}
          </dd>
        </div>
        <div>
          <dt>location</dt>
          <dd>{displayLocation(p) ?? "—"}</dd>
        </div>
        <div>
          <dt>activity</dt>
          <dd>{new Date(activityIso(p)).toLocaleDateString("en-CA")}</dd>
        </div>
      </dl>

      {/* Salary gets its own block rather than a fourth `panel-meta` cell: when the guarded range
          is suppressed we fall back to the posting's own wording, which is often a full sentence
          and would blow out the meta grid (D-087). Always rendered, so "not listed" is a readable
          answer rather than a missing feature. */}
      <div className="panel-salary">
        <span className="label">salary</span>
        <p className="salary-value">{p.comp_display ?? p.comp_raw ?? "Not listed"}</p>
        {/* The posting's own wording, kept whenever it says more than the formatted range does —
            the range is derived, this is the source. */}
        {p.comp_display && p.comp_raw && p.comp_raw !== p.comp_display && (
          <p className="salary-raw">{p.comp_raw}</p>
        )}
      </div>

      {/* Explicitly gated on `locked` as well as on the data: a public row carries no rationale,
          but relying on that alone would make the anti-leak guarantee a property of the API
          response rather than of this component. */}
      {!locked && p.rationale && <p className="rationale">{p.rationale}</p>}

      {!locked && (p.fits?.length || p.gaps?.length) && (
        <div className="fits-gaps">
          <div className="fits">
            <span className="label">fits</span>
            <ul>
              {(p.fits ?? []).map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          </div>
          <div className="gaps">
            <span className="label">gaps</span>
            <ul>
              {(p.gaps ?? []).map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* The posting's own words, last: the match write-up above is what this product adds, the
          description is the source it reasoned over. Absent bodies render nothing at all. */}
      {description === undefined && <div className="panel-description-loading" aria-hidden />}
      {typeof description === "string" && (
        <div className="panel-description">
          <span className="label">description</span>
          <p className="description-text">{description}</p>
        </div>
      )}

      {p.apply_url && (
        <a className="panel-apply" href={p.apply_url} target="_blank" rel="noreferrer">
          apply ↗
        </a>
      )}
    </aside>
  );
}
