import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, FEEDBACK_MAX_CHARS, sendFeedback } from "../api";
import { FeedbackDialog } from "./FeedbackDialog";

// Keep the real ApiError (error mapping branches on `instanceof`); mock only the network call.
vi.mock("../api", async (importActual) => {
  const actual = await importActual<typeof import("../api")>();
  return { ...actual, sendFeedback: vi.fn() };
});

const mockSend = vi.mocked(sendFeedback);

function renderDialog(onClose = vi.fn()) {
  render(<FeedbackDialog page="/dashboard" onClose={onClose} />);
  return onClose;
}

function textarea() {
  return screen.getByLabelText(/details/i);
}

// Matches both the idle "Send" and the in-flight "Sending…" label.
function sendButton() {
  return screen.getByRole("button", { name: /^Send/ });
}

describe("FeedbackDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSend.mockResolvedValue(undefined);
  });

  // --- the send path ---

  it("sends the category, the trimmed message, and the page it was opened from", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("button", { name: "Idea" }));
    await user.type(textarea(), "  Sort by salary  ");
    await user.click(sendButton());

    await waitFor(() => expect(mockSend).toHaveBeenCalledWith("idea", "Sort by salary", "/dashboard"));
  });

  it("defaults to the bug category", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.type(textarea(), "broken");
    await user.click(sendButton());

    await waitFor(() => expect(mockSend).toHaveBeenCalledWith("bug", "broken", "/dashboard"));
  });

  it("acknowledges a successful send instead of closing straight away", async () => {
    const user = userEvent.setup();
    const onClose = renderDialog();

    await user.type(textarea(), "nice work");
    await user.click(sendButton());

    expect(await screen.findByText(/thank you/i)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(onClose).toHaveBeenCalled();
  });

  // --- what you cannot send ---

  it("cannot send an empty or whitespace-only message", async () => {
    const user = userEvent.setup();
    renderDialog();

    expect(sendButton()).toBeDisabled();
    await user.type(textarea(), "   ");
    expect(sendButton()).toBeDisabled();
    expect(mockSend).not.toHaveBeenCalled();
  });

  it("cannot send past the length cap, and says how far over it is", () => {
    renderDialog();

    // A bulk change event: typing 5001 characters one keystroke at a time would take minutes.
    fireEvent.change(textarea(), { target: { value: "x".repeat(FEEDBACK_MAX_CHARS + 1) } });

    expect(sendButton()).toBeDisabled();
    expect(
      screen.getByText(`${FEEDBACK_MAX_CHARS + 1} / ${FEEDBACK_MAX_CHARS}`),
    ).toBeInTheDocument();
    expect(mockSend).not.toHaveBeenCalled();
  });

  // --- failure keeps the user's words ---

  it("keeps the typed text when the send fails, so Send is a real retry", async () => {
    const user = userEvent.setup();
    mockSend.mockRejectedValueOnce(new ApiError(502, "Couldn't send your feedback."));
    renderDialog();

    await user.type(textarea(), "the panel is blank");
    await user.click(sendButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't send your feedback.");
    expect(textarea()).toHaveValue("the panel is blank");

    mockSend.mockResolvedValueOnce(undefined);
    await user.click(sendButton());
    expect(await screen.findByText(/thank you/i)).toBeInTheDocument();
  });

  it("reports a transport failure in plain language", async () => {
    const user = userEvent.setup();
    mockSend.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    renderDialog();

    await user.type(textarea(), "hello");
    await user.click(sendButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach the server/i);
  });

  // --- dismissal ---

  it("closes on Escape and on a backdrop click", async () => {
    const user = userEvent.setup();
    const onClose = renderDialog();

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);

    await user.click(screen.getByTestId("feedback-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it("cannot be dismissed mid-send", async () => {
    const user = userEvent.setup();
    let release: () => void = () => undefined;
    mockSend.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        release = resolve;
      }),
    );
    const onClose = renderDialog();

    await user.type(textarea(), "wait for it");
    await user.click(sendButton());
    await waitFor(() => expect(sendButton()).toHaveTextContent("Sending…"));

    await user.keyboard("{Escape}");
    await user.click(screen.getByTestId("feedback-backdrop"));
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();

    await act(async () => {
      release();
    });
    expect(await screen.findByText(/thank you/i)).toBeInTheDocument();
  });

  // --- a11y + copy ---

  it("is a focused modal dialog", () => {
    renderDialog();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveFocus();
  });

  it("uses no em dashes in anything the user reads (D-099)", () => {
    const { container } = render(<FeedbackDialog page="/dashboard" onClose={vi.fn()} />);
    expect(container.textContent).not.toContain("—");
  });
});
