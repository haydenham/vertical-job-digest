import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Controls, type ControlState } from "./Controls";

const STATE: ControlState = {
  window: "all",
  view: "matched",
};

describe("Controls", () => {
  it("emits the chosen recency window", async () => {
    const onChange = vi.fn();
    render(<Controls state={STATE} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "1 week" }));
    expect(onChange).toHaveBeenCalledWith({ ...STATE, window: "week" });
  });

  it("marks the active window as pressed", () => {
    render(<Controls state={{ ...STATE, window: "new_today" }} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "New today" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("emits the chosen match view and marks the active one pressed", async () => {
    const onChange = vi.fn();
    render(<Controls state={STATE} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "Matched for you" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "All in-scope" }));
    expect(onChange).toHaveBeenCalledWith({ ...STATE, view: "cleaned" });
  });

  // --- the public demo board (D-105) -----------------------------------------------------------

  it("locked: still renders both view buttons, because the split is the product", () => {
    render(<Controls state={STATE} onLockedView={vi.fn()} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /matched for you/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All in-scope" })).toBeInTheDocument();
  });

  it("locked: 'Matched for you' asks for sign-in instead of switching the view", async () => {
    const onChange = vi.fn();
    const onLockedView = vi.fn();
    render(
      <Controls
        state={{ ...STATE, view: "cleaned" }}
        onLockedView={onLockedView}
        onChange={onChange}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /matched for you/i }));
    expect(onLockedView).toHaveBeenCalledTimes(1);
    // The state must not move: there is no résumé behind that view, so emitting it would ask the
    // board to render something that cannot exist.
    expect(onChange).not.toHaveBeenCalled();
  });

  it("locked: recency still works — it needs no résumé", async () => {
    const onChange = vi.fn();
    render(<Controls state={STATE} onLockedView={vi.fn()} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "1 week" }));
    expect(onChange).toHaveBeenCalledWith({ ...STATE, window: "week" });
  });

  it("locked: the locked button says why it is locked", () => {
    render(<Controls state={STATE} onLockedView={vi.fn()} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /matched for you/i })).toHaveAttribute(
      "title",
      expect.stringMatching(/sign in and upload a résumé/i),
    );
  });

  it("explains the exact recency and view semantics in native tooltips", () => {
    render(<Controls state={STATE} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "New today" })).toHaveAttribute(
      "title",
      expect.stringMatching(/first seen today/i),
    );
    expect(screen.getByRole("button", { name: "All in-scope" })).toHaveAttribute(
      "title",
      expect.stringMatching(/including unassessed/i),
    );
  });
});
