import { useState } from "react";

import type { PostingRow } from "../api";
import { MatchCell } from "./Verdict";

// Activity date = the ATS posted/updated date if known, else when we first saw it (mirrors the
// API's COALESCE(source_updated_at, first_seen_at) — D-024/D-030). Shown as a short UTC date.
function activityDate(p: PostingRow): string {
  const iso = p.source_updated_at ?? p.first_seen_at;
  return new Date(iso).toLocaleDateString("en-CA"); // YYYY-MM-DD
}

function DetailPanel({ p }: { p: PostingRow }) {
  return (
    <div className="detail">
      {p.rationale && <div className="rationale">{p.rationale}</div>}
      {(p.fits?.length || p.gaps?.length) && (
        <div className="fits-gaps">
          <div className="fits">
            <span className="label">fits</span>
            <ul>{(p.fits ?? []).map((f, i) => <li key={i}>{f}</li>)}</ul>
          </div>
          <div className="gaps">
            <span className="label">gaps</span>
            <ul>{(p.gaps ?? []).map((g, i) => <li key={i}>{g}</li>)}</ul>
          </div>
        </div>
      )}
      {p.apply_url && (
        <a className="apply" href={p.apply_url} target="_blank" rel="noreferrer">
          apply ↗
        </a>
      )}
    </div>
  );
}

function Row({ p }: { p: PostingRow }) {
  const [open, setOpen] = useState(false);
  const rejected = p.verdict === "no";
  return (
    <>
      <div
        className={`row${open ? " expanded" : ""}${rejected ? " rejected" : ""}`}
        onClick={() => setOpen((v) => !v)}
        role="button"
        aria-expanded={open}
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
        </span>
        <span className="cell-location">{p.location ?? "—"}</span>
        <span className="cell-date">{activityDate(p)}</span>
        <MatchCell verdict={p.verdict} score={p.score} />
      </div>
      {open && <DetailPanel p={p} />}
    </>
  );
}

export function PostingsTable({ postings }: { postings: PostingRow[] }) {
  return (
    <div className="table">
      <div className="row head">
        <span className="label">company</span>
        <span className="label">title</span>
        <span className="label">location</span>
        <span className="label">activity</span>
        <span className="label" style={{ textAlign: "right" }}>
          match
        </span>
      </div>
      {postings.map((p) => (
        <Row key={p.posting_id} p={p} />
      ))}
    </div>
  );
}
