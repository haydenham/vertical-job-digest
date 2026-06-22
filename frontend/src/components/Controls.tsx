import type { View, Window } from "../api";

const WINDOWS: { value: Window; label: string }[] = [
  { value: "new_today", label: "new today" },
  { value: "week", label: "1 wk" },
  { value: "two_weeks", label: "2 wk" },
  { value: "all", label: "all open" },
];

const VIEWS: { value: View; label: string }[] = [
  { value: "matched", label: "matched" },
  { value: "cleaned", label: "all cleaned" },
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
