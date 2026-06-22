import { useEffect, useState } from "react";

import { fetchPostings, fetchVerticals, type PostingsResponse } from "./api";
import { Controls, type ControlState } from "./components/Controls";
import { PostingsTable } from "./components/PostingsTable";

const INITIAL: ControlState = {
  window: "all",
  includeUnassessed: false,
  includeRejected: false,
};

export default function App() {
  const [vertical, setVertical] = useState<string | null>(null);
  const [controls, setControls] = useState<ControlState>(INITIAL);
  const [data, setData] = useState<PostingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Resolve the vertical once (no slug hardcoded — D-042); the picker defaults to the first.
  useEffect(() => {
    fetchVerticals()
      .then((vs) => {
        if (vs.length === 0) {
          setError("no active vertical");
          setLoading(false);
        } else {
          setVertical(vs[0]);
        }
      })
      .catch((e: unknown) => {
        setError(String(e));
        setLoading(false);
      });
  }, []);

  // Refetch whenever the vertical or any toggle changes.
  useEffect(() => {
    if (vertical === null) return;
    setLoading(true);
    setError(null);
    fetchPostings({
      vertical,
      window: controls.window,
      includeUnassessed: controls.includeUnassessed,
      includeRejected: controls.includeRejected,
    })
      .then((resp) => setData(resp))
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [vertical, controls]);

  return (
    <div className="app">
      <header className="header">
        <span className="wordmark">
          <span className="prompt">$</span> vja<span className="cursor">▮</span>
        </span>
        <span className="meta">
          {vertical && <span className="accent">~/{vertical}</span>}
          {data && ` · ${data.count} open`}
        </span>
      </header>

      <Controls state={controls} onChange={setControls} />

      {error ? (
        <div className="notice error">// {error}</div>
      ) : loading ? (
        <div className="notice">loading…</div>
      ) : data && data.postings.length > 0 ? (
        <PostingsTable postings={data.postings} />
      ) : (
        <div className="notice">// no postings match these filters</div>
      )}

      <footer className="footer">
        <span className="kbd">↵ open</span> to expand a row · read-only · updates nightly
      </footer>
    </div>
  );
}
