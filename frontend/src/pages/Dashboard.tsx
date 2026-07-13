import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { fetchPostings, type PostingsResponse } from "../api";
import { Controls, type ControlState } from "../components/Controls";
import { PostingPanel } from "../components/PostingPanel";
import { PostingsTable } from "../components/PostingsTable";
import { DEFAULT_SORT, filterPostings, sortPostings, type SortState } from "../postingsView";

const INITIAL: ControlState = {
  window: "all",
  view: "matched",
};

// B-3: right after onboarding the matched view can be empty while the signup backfill computes.
// Poll it client-side (no backend push / status endpoint — honours D-057) until matches land or a
// bounded timeout, then fall back to "results after tonight's run".
const POLL_INTERVAL_MS = 10_000;
const POLL_TIMEOUT_MS = 150_000; // ~2.5 min

// The read-only dashboard (Phase 6 · B2), now for a SINGLE vertical passed in by the route — the
// user's own (`useAuth().profile.vertical`), never a global picker (the D-064 fix). Fetches are
// credentialed (api.ts), so the server resolves this user's profile + match quality.
export function Dashboard({ vertical }: { vertical: string }) {
  const location = useLocation();
  const justOnboarded = Boolean(
    (location.state as { justOnboarded?: boolean } | null)?.justOnboarded,
  );

  const [controls, setControls] = useState<ControlState>(INITIAL);
  const [data, setData] = useState<PostingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  const [pollTimedOut, setPollTimedOut] = useState(false);

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

  // Poll the matched view while the freshly-triggered backfill has yet to produce any matches.
  const awaitingMatches =
    justOnboarded &&
    controls.view === "matched" &&
    data !== null &&
    data.count === 0 &&
    !pollTimedOut;

  useEffect(() => {
    if (!awaitingMatches) return;
    const startedAt = Date.now();
    const id = setInterval(() => {
      if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
        setPollTimedOut(true);
      } else {
        setReloadKey((k) => k + 1);
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [awaitingMatches]);

  const emptyMatchedAfterOnboard =
    justOnboarded && controls.view === "matched" && data !== null && data.count === 0;

  const visible = data ? sortPostings(filterPostings(data.postings, query), sort) : [];
  const filtering = query.trim() !== "";
  // Selection survives refetches only while the posting is still present — a poll/toggle that
  // drops it closes the panel naturally via this lookup.
  const selected = data?.postings.find((p) => p.posting_id === selectedId) ?? null;

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
          <span className="accent">{vertical}</span>
          {data && (filtering ? `${visible.length} of ${data.count}` : `${data.count} open`)}
        </span>
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
      ) : awaitingMatches ? (
        <div className="notice">finding your matches… (this updates as they’re computed)</div>
      ) : emptyMatchedAfterOnboard ? (
        <div className="notice">
          matches update as they’re computed — full results after tonight’s run
        </div>
      ) : (
        <div className="notice">No postings match these filters</div>
      )}

      {selected && <PostingPanel p={selected} onClose={() => setSelectedId(null)} />}

      <footer className="footer">Click a row for details · read-only · updates nightly</footer>
    </>
  );
}
