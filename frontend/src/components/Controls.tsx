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
export function Controls({
  state,
  onChange,
}: {
  state: ControlState;
  onChange: (next: ControlState) => void;
}) {
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
          {VIEWS.map((v) => (
            <button
              key={v.value}
              type="button"
              aria-pressed={state.view === v.value}
              title={v.title}
              onClick={() => onChange({ ...state, view: v.value })}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
