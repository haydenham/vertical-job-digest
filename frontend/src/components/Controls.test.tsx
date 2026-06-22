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

  it("emits the chosen match view and marks the active one pressed", async () => {
    const onChange = vi.fn();
    render(<Controls state={STATE} onChange={onChange} />);
    expect(screen.getByRole("button", { name: "matched" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "all cleaned" }));
    expect(onChange).toHaveBeenCalledWith({ ...STATE, view: "cleaned" });
  });
});
