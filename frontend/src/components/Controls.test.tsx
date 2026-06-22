import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Controls, type ControlState } from "./Controls";

const STATE: ControlState = {
  window: "all",
  includeUnassessed: false,
  includeRejected: false,
};

describe("Controls", () => {
  it("emits the chosen recency window", async () => {
    const onChange = vi.fn();
    render(<Controls state={STATE} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "1 wk" }));
    expect(onChange).toHaveBeenCalledWith({ ...STATE, window: "week" });
  });

  it("marks the active window as pressed", () => {
    render(<Controls state={{ ...STATE, window: "new_today" }} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "new today" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("emits match-status toggle changes", async () => {
    const onChange = vi.fn();
    render(<Controls state={STATE} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText("unassessed"));
    expect(onChange).toHaveBeenCalledWith({ ...STATE, includeUnassessed: true });
    await userEvent.click(screen.getByLabelText("rejected"));
    expect(onChange).toHaveBeenCalledWith({ ...STATE, includeRejected: true });
  });
});
