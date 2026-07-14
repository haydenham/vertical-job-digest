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
