import { Link } from "react-router-dom";

import type { DisplayPosting } from "../api";
import { NATURAL_DIR, activityIso, displayLocation, type SortKey, type SortState } from "../postingsView";
import { MatchCell } from "./Verdict";

// Activity date shown as a short UTC-ish date (see postingsView.activityIso — D-024/D-030).
function activityDate(p: DisplayPosting): string {
  return new Date(activityIso(p)).toLocaleDateString("en-CA"); // YYYY-MM-DD
}

const COLUMNS: { key: SortKey; label: string; right?: boolean }[] = [
  { key: "company", label: "company" },
  { key: "title", label: "title" },
  { key: "location", label: "location" },
  { key: "activity", label: "activity" },
  { key: "score", label: "match", right: true },
];

// The demo board's stand-in for the match cell (D-105). The column stays — the table's shape is
// the dashboard's — and what would be a verdict is the offer to go and get one. A link, not a
// button, because the label says "sign in" and that is exactly what clicking it does.
function LockedMatchCell() {
  return (
    <span className="cell-match locked">
      <Link to="/login" className="match-lock" onClick={(e) => e.stopPropagation()}>
        <span aria-hidden="true">□</span> sign in
      </Link>
    </span>
  );
}

function Row({
  p,
  selected,
  locked,
  onSelect,
}: {
  p: DisplayPosting;
  selected: boolean;
  locked: boolean;
  onSelect: (id: number) => void;
}) {
  const rejected = p.verdict === "no";
  const spine = p.verdict ? ` v-${p.verdict}` : "";
  return (
    <div
      className={`row${spine}${selected ? " selected" : ""}${rejected ? " rejected" : ""}`}
      onClick={() => onSelect(p.posting_id)}
      role="button"
      aria-expanded={selected}
    >
      <span className="cell-company">{p.company}</span>
      <span className="cell-title">
        {p.apply_url ? (
          <a href={p.apply_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
            {p.title ?? "(untitled)"}
          </a>
        ) : (
          (p.title ?? "(untitled)")
        )}
        {p.rationale && <span className="cell-snippet">{p.rationale}</span>}
      </span>
      <span className="cell-location">{displayLocation(p) ?? "—"}</span>
      <span className="cell-date">{activityDate(p)}</span>
      {locked ? <LockedMatchCell /> : <MatchCell verdict={p.verdict ?? null} score={p.score ?? null} />}
      {/* Persistent affordance that the row opens a detail panel (D-087). Decorative only — the
          row itself already carries role="button" + aria-expanded, so this is hidden from AT. */}
      <span className="cell-chevron" aria-hidden="true">
        ›
      </span>
    </div>
  );
}

// Controlled table (PR 3, D-080): sort + selection live in the Dashboard; rows carry the match
// verdict at row level (spine + snippet) and a click opens the side panel, not an inline expand.
export function PostingsTable({
  postings,
  sort,
  onSort,
  selectedId,
  locked = false,
  onSelect,
}: {
  postings: DisplayPosting[];
  sort: SortState;
  onSort: (next: SortState) => void;
  selectedId: number | null;
  // The public demo board (D-105): identical table, with the match column locked behind sign-in.
  locked?: boolean;
  onSelect: (id: number) => void;
}) {
  function headClick(key: SortKey) {
    // Sorting a column whose every cell is the same lock would silently do nothing; leaving the
    // header inert is more honest than a control that appears to work.
    if (locked && key === "score") return;
    onSort(sort.key === key ? { key, dir: sort.dir === "asc" ? "desc" : "asc" } : { key, dir: NATURAL_DIR[key] });
  }
  return (
    <div className="table">
      <div className="row head">
        {COLUMNS.map((c) => (
          <span
            key={c.key}
            className={c.right ? "head-right" : undefined}
            aria-sort={sort.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}
          >
            <button
              type="button"
              className={`sort-btn${c.right ? " sort-right" : ""}${sort.key === c.key ? " active" : ""}`}
              onClick={() => headClick(c.key)}
            >
              {c.label}
              {sort.key === c.key && <span className="sort-arrow">{sort.dir === "asc" ? "▲" : "▼"}</span>}
            </button>
          </span>
        ))}
        {/* spacer keeping the header aligned with the rows' chevron track */}
        <span aria-hidden="true" />
      </div>
      {postings.map((p) => (
        <Row
          key={p.posting_id}
          p={p}
          selected={p.posting_id === selectedId}
          locked={locked}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
