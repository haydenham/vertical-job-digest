import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WelcomeTour } from "./WelcomeTour";

describe("WelcomeTour", () => {
  it("walks forward and back through all four approved slides", async () => {
    const onDismiss = vi.fn();
    render(<WelcomeTour onDismiss={onDismiss} />);

    expect(screen.getByRole("dialog", { name: /your rolefeed, updated every 4 hours/i })).toBeInTheDocument();
    expect(screen.getByText("1 of 4")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading", { name: "Matched for you" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("heading", { name: /your rolefeed, updated every 4 hours/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading", { name: /explore every in-scope role/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading", { name: /open details and keep your résumé current/i })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Start exploring" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("dismisses from Skip, Escape, or a click on the backdrop but not inside", async () => {
    const onDismiss = vi.fn();
    const { rerender } = render(<WelcomeTour onDismiss={onDismiss} />);

    fireEvent.mouseDown(screen.getByRole("dialog"));
    expect(onDismiss).not.toHaveBeenCalled();
    fireEvent.mouseDown(screen.getByTestId("welcome-tour-backdrop"));
    expect(onDismiss).toHaveBeenCalledTimes(1);

    rerender(<WelcomeTour onDismiss={onDismiss} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onDismiss).toHaveBeenCalledTimes(2);

    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onDismiss).toHaveBeenCalledTimes(3);
  });
});
