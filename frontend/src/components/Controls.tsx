import type { View, Window } from "../api";

const WINDOWS: { value: Window; label: string; title: string }[] = [
  {
    value: "new_today",
    label: "New today",
    title: "Roles first seen today: the same new roles eligible for today's digest.",
  },
  { value: "week", label: "1 week", title: "Roles posted or updated within the last 7 days." },
  {
    value: "two_weeks",
    label: "2 weeks",
    title: "Roles posted or updated within the last 14 days.",
  },
  { value: "all", label: "All open", title: "Every open in-scope role in this vertical." },
];

const VIEWS: { value: View; label: string; title: string }[] = [
  {
    value: "matched",
    label: "Matched for you",
    title: "Roles recommended for your current résumé: strong yes, yes, or maybe.",
  },
  {
    value: "cleaned",
    label: "All in-scope",
    title: "Every open in-scope role, including unassessed roles and roles not recommended.",
  },
];

export interface ControlState {
  window: Window;
  view: View;
}

// The dashboard's two orthogonal axes (D-043): recency (segmented) and match-status view
// (segmented: matched vs all-cleaned). Stateless — renders `state` and emits the next state up.
//
// `onLockedView` turns this into the public demo board's control (D-105): its presence is what
// locks "Matched for you". Both view buttons still render, because the matched/all-in-scope split
// IS the product and hiding it would sell the demo short — but that view needs a résumé, so the
// button calls this handler (sign-in) instead of emitting a state change it cannot honour.
// Recency needs no résumé and stays fully live.
//
// A callback rather than a `useNavigate` here on purpose: this component stays free of router
// context, so it (and the dashboard that renders it) keeps rendering in a bare test.
export function Controls({
  state,
  onLockedView,
  onChange,
}: {
  state: ControlState;
  onLockedView?: () => void;
  onChange: (next: ControlState) => void;
}) {
  const locked = onLockedView !== undefined;
  return (
    <div className="controls">
      <div className="control-group">
        <span className="label">recency</span>
        <div className="segmented" role="group" aria-label="recency window">
          {WINDOWS.map((w) => (
            <button
              key={w.value}
              type="button"
              aria-pressed={state.window === w.value}
              title={w.title}
              onClick={() => onChange({ ...state, window: w.value })}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      <div className="control-group">
        <span className="label">show</span>
        <div className="segmented" role="group" aria-label="match view">
          {VIEWS.map((v) => {
            const needsResume = locked && v.value === "matched";
            return (
              <button
                key={v.value}
                type="button"
                aria-pressed={state.view === v.value}
                title={needsResume ? "Sign in and upload a résumé to see your matches." : v.title}
                onClick={() =>
                  needsResume ? onLockedView?.() : onChange({ ...state, view: v.value })
                }
              >
                {needsResume && (
                  <span className="view-lock" aria-hidden="true">
                    □{" "}
                  </span>
                )}
                {v.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
