import { useEffect, useRef } from "react";

import type { PostingRow } from "../api";
import { activityIso } from "../postingsView";
import { MatchCell } from "./Verdict";

// Overlay detail panel (PR 3, D-080): slides over the right side of the table — the table keeps
// full width underneath. Esc or a click outside closes; clicking another row closes on mousedown
// then re-selects on click, so the panel switches postings in place.
export function PostingPanel({ p, onClose }: { p: PostingRow; onClose: () => void }) {
  const ref = useRef<HTMLElement>(null);

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
            <MatchCell verdict={p.verdict} score={p.score} />
          </dd>
        </div>
        <div>
          <dt>location</dt>
          <dd>{p.location ?? "—"}</dd>
        </div>
        <div>
          <dt>activity</dt>
          <dd>{new Date(activityIso(p)).toLocaleDateString("en-CA")}</dd>
        </div>
      </dl>

      {p.rationale && <p className="rationale">{p.rationale}</p>}

      {(p.fits?.length || p.gaps?.length) && (
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

      {p.apply_url && (
        <a className="panel-apply" href={p.apply_url} target="_blank" rel="noreferrer">
          apply ↗
        </a>
      )}
    </aside>
  );
}
