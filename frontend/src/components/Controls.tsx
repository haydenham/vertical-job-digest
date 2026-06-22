import type { Window } from "../api";

const WINDOWS: { value: Window; label: string }[] = [
  { value: "new_today", label: "new today" },
  { value: "week", label: "1 wk" },
  { value: "two_weeks", label: "2 wk" },
  { value: "all", label: "all open" },
];

export interface ControlState {
  window: Window;
  includeUnassessed: boolean;
  includeRejected: boolean;
}

// The dashboard's two orthogonal axes (D-041): recency (segmented control) and match-status
// (two checkboxes). Stateless — it renders `state` and emits the next state up via `onChange`.
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
        <div className="checks">
          <label className="check">
            <input
              type="checkbox"
              checked={state.includeUnassessed}
              onChange={(e) =>
                onChange({ ...state, includeUnassessed: e.target.checked })
              }
            />
            unassessed
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={state.includeRejected}
              onChange={(e) =>
                onChange({ ...state, includeRejected: e.target.checked })
              }
            />
            rejected
          </label>
        </div>
      </div>
    </div>
  );
}
