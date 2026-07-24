import { useEffect, useState } from "react";

import { fetchPostings, type PostingsResponse } from "../api";
import { useAuth } from "../auth/useAuth";
import { Controls, type ControlState } from "../components/Controls";
import { PostingPanel } from "../components/PostingPanel";
import { PostingsTable } from "../components/PostingsTable";
import { DEFAULT_SORT, filterPostings, sortPostings, type SortState } from "../postingsView";
import { verticalCopy } from "../verticalCopy";

const INITIAL: ControlState = {
  window: "all",
  view: "matched",
};

// While the signup/reupload backfill computes, `/api/me` reports `backfill_status: "running"`
// (D-082 — the endpoint stamps `started` before scheduling, so this is race-free). We poll both
// the status (silent auth refresh) and the postings until the server flips it to "done"; the
// server's own 10-min staleness guard bounds the poll, so no client timeout is needed. This
// replaces the old blind `justOnboarded` router-state poll — it survives refresh and fires on
// reupload too.
const POLL_INTERVAL_MS = 10_000;

// The read-only dashboard (Phase 6 · B2), now for a SINGLE vertical passed in by the route — the
// user's own (`useAuth().profile.vertical`), never a global picker (the D-064 fix). Fetches are
// credentialed (api.ts), so the server resolves this user's profile + match quality.
export function Dashboard({ vertical }: { vertical: string }) {
  const { profile, refresh } = useAuth();
  const matching = profile?.backfill_status === "running";

  const [controls, setControls] = useState<ControlState>(INITIAL);
  const [data, setData] = useState<PostingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  // Client-side presentation state (PR 3, D-080): the API returns the full filtered set
  // server-sorted by freshness, so filter/sort never refetch.
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortState>(DEFAULT_SORT);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Refetch on vertical / toggle change, and on each poll tick (reloadKey bump).
  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchPostings({ vertical, window: controls.window, view: controls.view })
      .then((resp) => setData(resp))
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [vertical, controls, reloadKey]);

  // While matching: re-probe the status (silently — no route blanking) and stream in the rows
  // computed so far. The interval dissolves when the server reports done.
  useEffect(() => {
    if (!matching) return;
    const id = setInterval(() => {
      void refresh({ silent: true }).catch(() => undefined); // transient probe failures: next tick
      setReloadKey((k) => k + 1);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [matching, refresh]);

  const visible = data ? sortPostings(filterPostings(data.postings, query), sort) : [];
  const filtering = query.trim() !== "";
  // Selection survives refetches only while the posting is still present — a poll/toggle that
  // drops it closes the panel naturally via this lookup.
  const selected = data?.postings.find((p) => p.posting_id === selectedId) ?? null;

  const emptyMatched = controls.view === "matched" && data !== null && data.count === 0;

  return (
    <>
      <div className="subbar">
        <Controls state={controls} onChange={setControls} />
        <input
          type="search"
          className="filter-input"
          placeholder="Filter by company, title, location…"
          aria-label="Filter postings"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="meta">
          <span className="accent">{verticalCopy(vertical).name}</span>
          {data && (filtering ? `${visible.length} of ${data.count}` : `${data.count} open`)}
        </span>
      </div>

      {matching && (
        <div className="notice busy banner" role="status">
          <span className="spinner" aria-hidden="true" />
          Matching in progress — results update live
        </div>
      )}

      <div className="table-guide">
        Click a row for salary, match rationale, and apply link · read-only · updates nightly
      </div>

      {error ? (
        <div className="notice error">{error}</div>
      ) : loading && data === null ? (
        // Only the very first load blanks the page — refetches (poll ticks, toggle changes)
        // keep the previous rows/notice in place instead of flashing "loading…" (D-082).
        <div className="notice">loading…</div>
      ) : visible.length > 0 ? (
        <PostingsTable
          postings={visible}
          sort={sort}
          onSort={setSort}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      ) : data && data.postings.length > 0 ? (
        <div className="notice">No postings match “{query.trim()}”</div>
      ) : emptyMatched && matching ? (
        <div className="notice">Matches appear here as they’re computed.</div>
      ) : emptyMatched && profile?.backfill_status === "done" ? (
        <div className="notice">No matches yet — full results after tonight’s run.</div>
      ) : (
        <div className="notice">No postings match these filters</div>
      )}

      {selected && <PostingPanel p={selected} onClose={() => setSelectedId(null)} />}
    </>
  );
}
