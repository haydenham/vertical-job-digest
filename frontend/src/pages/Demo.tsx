import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import {
  fetchPublicPostings,
  fetchPublicVerticals,
  type PublicPostingsResponse,
  type PublicVertical,
} from "../api";
import { Controls, type ControlState } from "../components/Controls";
import { PostingPanel } from "../components/PostingPanel";
import { PostingsTable } from "../components/PostingsTable";
import { DEFAULT_SORT, filterPostings, sortPostings, type SortState } from "../postingsView";
import { verticalCopy } from "../verticalCopy";

// `cleaned` is not a user choice here: with no résumé there is nothing to be matched against, so
// the board is always the objective in-scope universe (D-045). `Controls` still renders both view
// buttons in locked mode — the locked one routes to sign-in rather than switching.
const INITIAL: ControlState = {
  window: "all",
  view: "cleaned",
};

// The public demo board (D-105). This IS the dashboard — same subbar, same table, same detail
// panel, same live data — rendered for someone with no account. The only difference is that
// everything résumé-derived is replaced by an invitation to sign in, never by a fabrication.
//
// It exists because the funnel, not the pipeline, was the constraint: the launch measured 5,000
// views against 10 résumé uploads, so ~99.9% of interest never saw a single job. The first route
// in the app with no `useAuth` guard.
export function Demo() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const requested = params.get("vertical");

  const [verticals, setVerticals] = useState<PublicVertical[] | null>(null);
  const [vertical, setVertical] = useState<string | null>(null);
  const [controls, setControls] = useState<ControlState>(INITIAL);
  const [data, setData] = useState<PublicPostingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortState>(DEFAULT_SORT);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // The toggle's options come from the server with counts attached, so a vertical with nothing
  // open is never offered. `?vertical=` wins when it names one of them — that is what lets a
  // single-vertical post link straight at its own board — otherwise we open on the fullest one,
  // which the endpoint already returns first.
  useEffect(() => {
    let live = true;
    fetchPublicVerticals()
      .then((rows) => {
        if (!live) return;
        setVerticals(rows);
        const wanted = rows.find((r) => r.vertical === requested);
        setVertical(wanted?.vertical ?? rows[0]?.vertical ?? null);
      })
      .catch(() => {
        if (live) {
          setVerticals([]);
          setError("We couldn't load the board just now. Please try again in a moment.");
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
    // Deliberately once on mount: `?vertical=` picks the *initial* board, and re-running this on
    // every URL change would fight the toggle below for control of it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (vertical === null) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setSelectedId(null);
    fetchPublicPostings(vertical, controls.window, controller.signal)
      .then((resp) => setData(resp))
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(String(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [vertical, controls.window]);

  const visible = useMemo(
    () => (data ? sortPostings(filterPostings(data.postings, query), sort) : []),
    [data, query, sort],
  );
  const filtering = query.trim() !== "";
  const selected = data?.postings.find((p) => p.posting_id === selectedId) ?? null;

  function chooseVertical(next: string) {
    setVertical(next);
    setQuery("");
    // Keep the address bar honest so the board is linkable and survives a refresh. `?src=` (the
    // campaign tag we read signups against) rides along untouched.
    const nextParams = new URLSearchParams(params);
    nextParams.set("vertical", next);
    setParams(nextParams, { replace: true });
  }

  return (
    <>
      <div className="demo-intro">
        <h1 className="demo-title">Every open role we track, right now</h1>
        <p className="demo-lede">
          This is the live board, not a sample. Rolefeed follows a curated set of companies in each
          vertical and checks their job boards every few hours.{" "}
          <Link to="/login" className="demo-cta">
            Sign in
          </Link>{" "}
          and upload a résumé to see which of these roles actually fit you.
        </p>
        {verticals !== null && verticals.length > 0 && (
          <div className="segmented demo-verticals" role="group" aria-label="vertical">
            {verticals.map((v) => (
              <button
                key={v.vertical}
                type="button"
                aria-pressed={v.vertical === vertical}
                onClick={() => chooseVertical(v.vertical)}
              >
                {verticalCopy(v.vertical).name}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="subbar">
        <Controls
          state={controls}
          onLockedView={() => navigate("/login")}
          onChange={setControls}
        />
        <input
          type="search"
          className="filter-input"
          placeholder="Filter by company, title, location…"
          aria-label="Filter postings"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="meta">
          {vertical && <span className="accent">{verticalCopy(vertical).name}</span>}
          {data && (filtering ? `${visible.length} of ${data.count}` : `${data.count} open`)}
        </span>
      </div>

      <div className="table-guide">
        Click a row for salary, the full description, and the apply link · read-only · updates every
        few hours
      </div>

      {error ? (
        <div className="notice error" role="alert">
          {error}
        </div>
      ) : loading && data === null ? (
        <div className="notice">loading…</div>
      ) : visible.length > 0 ? (
        <PostingsTable
          postings={visible}
          sort={sort}
          onSort={setSort}
          selectedId={selectedId}
          locked
          onSelect={setSelectedId}
        />
      ) : data && data.postings.length > 0 ? (
        <div className="notice">No postings match “{query.trim()}”</div>
      ) : (
        <div className="notice">No postings match these filters</div>
      )}

      {selected && vertical && (
        <PostingPanel
          p={selected}
          vertical={vertical}
          locked
          onClose={() => setSelectedId(null)}
        />
      )}
    </>
  );
}
