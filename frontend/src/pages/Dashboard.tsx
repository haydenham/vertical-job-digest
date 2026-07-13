import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { fetchPostings, type PostingsResponse } from "../api";
import { Controls, type ControlState } from "../components/Controls";
import { PostingsTable } from "../components/PostingsTable";

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

  return (
    <>
      <div className="subbar">
        <Controls state={controls} onChange={setControls} />
        <span className="meta">
          <span className="accent">{vertical}</span>
          {data && `${data.count} open`}
        </span>
      </div>

      {error ? (
        <div className="notice error">{error}</div>
      ) : loading ? (
        <div className="notice">loading…</div>
      ) : data && data.postings.length > 0 ? (
        <PostingsTable postings={data.postings} />
      ) : awaitingMatches ? (
        <div className="notice">finding your matches… (this updates as they’re computed)</div>
      ) : emptyMatchedAfterOnboard ? (
        <div className="notice">
          matches update as they’re computed — full results after tonight’s run
        </div>
      ) : (
        <div className="notice">No postings match these filters</div>
      )}

      <footer className="footer">Click a row to expand · read-only · updates nightly</footer>
    </>
  );
}
