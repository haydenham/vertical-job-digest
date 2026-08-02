import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, deleteAccount, fetchVerticals, setDigestPaused, switchVertical } from "../api";
import { useAuth, type AuthState } from "../auth/useAuth";
import { Settings } from "./Settings";

// Keep the real ApiError (error mapping branches on `instanceof`); mock only the network calls.
vi.mock("../api", async (importActual) => {
  const actual = await importActual<typeof import("../api")>();
  return {
    ...actual,
    setDigestPaused: vi.fn(),
    deleteAccount: vi.fn(),
    fetchVerticals: vi.fn(),
    switchVertical: vi.fn(),
  };
});
vi.mock("../auth/useAuth", () => ({ useAuth: vi.fn() }));

const mockSetPaused = vi.mocked(setDigestPaused);
const mockDelete = vi.mocked(deleteAccount);
const mockVerticals = vi.mocked(fetchVerticals);
const mockSwitch = vi.mocked(switchVertical);
const mockUseAuth = vi.mocked(useAuth);

const PROFILE = {
  vertical: "grid_power_software",
  resume_version: "v1",
  backfill_status: "done" as const,
};

function auth(over: Partial<AuthState> = {}): AuthState {
  return {
    user: { email: "a@b.co", name: "A", digest_paused: false },
    profile: null,
    loading: false,
    authError: false,
    refresh: vi.fn().mockResolvedValue(null),
    logout: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
}

/** Auth state for an onboarded user, with the vertical list already resolving. */
function onboarded(over: Partial<AuthState> = {}): AuthState {
  mockVerticals.mockResolvedValue([
    "aviation_software",
    "grid_power_software",
    "robotics_software",
  ]);
  return auth({ profile: PROFILE, ...over });
}

function renderSettings() {
  return render(
    <MemoryRouter initialEntries={["/settings"]}>
      <Routes>
        <Route path="/settings" element={<Settings />} />
        <Route path="/login" element={<div>login-page</div>} />
        <Route path="/" element={<div>root-page</div>} />
        <Route path="/dashboard" element={<div>dashboard-page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Settings", () => {
  beforeEach(() => vi.clearAllMocks());

  // --- guard ---

  it("redirects to login when logged out", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderSettings();
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });

  it("renders for a signed-in user with no profile (deletion must stay reachable)", () => {
    mockUseAuth.mockReturnValue(auth({ profile: null }));
    renderSettings();
    expect(screen.getByRole("switch")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete my account/i })).toBeInTheDocument();
  });

  // --- digest toggle ---

  it("switch is on while receiving and off while paused", () => {
    mockUseAuth.mockReturnValue(auth());
    const { unmount } = renderSettings();
    expect(screen.getByRole("switch")).toBeChecked();
    unmount();

    mockUseAuth.mockReturnValue(
      auth({ user: { email: "a@b.co", name: "A", digest_paused: true } }),
    );
    renderSettings();
    expect(screen.getByRole("switch")).not.toBeChecked();
    expect(screen.getByText(/digest emails are paused/i)).toBeInTheDocument();
  });

  it("flipping the switch pauses the digest and re-syncs /api/me", async () => {
    const state = auth();
    mockUseAuth.mockReturnValue(state);
    mockSetPaused.mockResolvedValue({ digest_paused: true, vertical: null });
    renderSettings();

    await userEvent.click(screen.getByRole("switch"));

    expect(mockSetPaused).toHaveBeenCalledWith(true);
    await waitFor(() => expect(state.refresh).toHaveBeenCalledWith({ silent: true }));
  });

  it("flipping the switch back resumes the digest", async () => {
    mockUseAuth.mockReturnValue(
      auth({ user: { email: "a@b.co", name: "A", digest_paused: true } }),
    );
    mockSetPaused.mockResolvedValue({ digest_paused: false, vertical: null });
    renderSettings();

    await userEvent.click(screen.getByRole("switch"));

    expect(mockSetPaused).toHaveBeenCalledWith(false);
  });

  it("a failed toggle shows an error and the switch stays put", async () => {
    const state = auth();
    mockUseAuth.mockReturnValue(state);
    mockSetPaused.mockRejectedValue(new ApiError(500, "boom"));
    renderSettings();

    await userEvent.click(screen.getByRole("switch"));

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    // Rendered from context truth, which never moved.
    expect(screen.getByRole("switch")).toBeChecked();
    expect(state.refresh).not.toHaveBeenCalled();
  });

  // --- account deletion ---

  it("delete opens the confirm dialog; Cancel closes it without deleting", async () => {
    mockUseAuth.mockReturnValue(auth());
    renderSettings();

    await userEvent.click(screen.getByRole("button", { name: /delete my account/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mockDelete).not.toHaveBeenCalled();
  });

  it("Escape closes the confirm dialog without deleting", async () => {
    mockUseAuth.mockReturnValue(auth());
    renderSettings();

    await userEvent.click(screen.getByRole("button", { name: /delete my account/i }));
    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(mockDelete).not.toHaveBeenCalled();
  });

  it("confirming deletes the account, clears the session, and lands on the root", async () => {
    const state = auth();
    mockUseAuth.mockReturnValue(state);
    mockDelete.mockResolvedValue(undefined);
    renderSettings();

    await userEvent.click(screen.getByRole("button", { name: /delete my account/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(
      // Two "Delete my account" buttons exist now (opener + confirm); confirm is in the dialog.
      screen.getAllByRole("button", { name: /^delete my account$/i }).find((b) =>
        dialog.contains(b),
      )!,
    );

    expect(mockDelete).toHaveBeenCalledOnce();
    await waitFor(() => expect(state.logout).toHaveBeenCalledOnce());
    expect(await screen.findByText("root-page")).toBeInTheDocument();
  });

  it("a failed deletion shows the error in the dialog and stays on settings", async () => {
    const state = auth();
    mockUseAuth.mockReturnValue(state);
    mockDelete.mockRejectedValue(new ApiError(500, "server exploded"));
    renderSettings();

    await userEvent.click(screen.getByRole("button", { name: /delete my account/i }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(
      screen.getAllByRole("button", { name: /^delete my account$/i }).find((b) =>
        dialog.contains(b),
      )!,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("server exploded");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(state.logout).not.toHaveBeenCalled();
    expect(screen.queryByText("root-page")).not.toBeInTheDocument();
  });

  it("a transport failure gets friendly copy, not a raw TypeError", async () => {
    mockUseAuth.mockReturnValue(auth());
    mockSetPaused.mockRejectedValue(new TypeError("Failed to fetch"));
    renderSettings();

    await userEvent.click(screen.getByRole("switch"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach the server/i);
  });

  // The back link targets `/`, not `/dashboard`: this page is login-gated only (D-094), so a
  // signed-in user with no profile can be here, and only the smart root routes all three cases.
  it("offers a back link to the smart root, not straight to the dashboard", async () => {
    mockUseAuth.mockReturnValue(auth());
    renderSettings();

    const back = screen.getByRole("link", { name: /back/i });
    expect(back).toHaveAttribute("href", "/");

    await userEvent.click(back);
    expect(await screen.findByText("root-page")).toBeInTheDocument();
  });

  it("keeps the back link available to a signed-in user with no profile yet", () => {
    mockUseAuth.mockReturnValue(auth({ profile: null }));
    renderSettings();
    expect(screen.getByRole("link", { name: /back/i })).toHaveAttribute("href", "/");
  });

  // --- vertical switching ---

  it("hides the vertical section for a user with no profile", () => {
    mockUseAuth.mockReturnValue(auth({ profile: null }));
    renderSettings();
    expect(screen.queryByRole("group", { name: /vertical/i })).not.toBeInTheDocument();
  });

  it("marks the user's current vertical as selected", async () => {
    mockUseAuth.mockReturnValue(onboarded());
    renderSettings();

    const grid = await screen.findByRole("button", { name: /energy & grid/i });
    expect(grid).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /robotics/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("choosing another vertical confirms first and never switches on the click alone", async () => {
    mockUseAuth.mockReturnValue(onboarded());
    renderSettings();

    await userEvent.click(await screen.findByRole("button", { name: /robotics/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(mockSwitch).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mockSwitch).not.toHaveBeenCalled();
  });

  it("clicking the current vertical does nothing", async () => {
    mockUseAuth.mockReturnValue(onboarded());
    renderSettings();

    await userEvent.click(await screen.findByRole("button", { name: /energy & grid/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mockSwitch).not.toHaveBeenCalled();
  });

  it("confirming switches, re-reads /api/me, and lands on the dashboard", async () => {
    const state = onboarded();
    mockUseAuth.mockReturnValue(state);
    mockSwitch.mockResolvedValue({ digest_paused: false, vertical: "robotics_software" });
    renderSettings();

    await userEvent.click(await screen.findByRole("button", { name: /robotics/i }));
    await userEvent.click(screen.getByRole("button", { name: /switch vertical/i }));

    expect(mockSwitch).toHaveBeenCalledWith("robotics_software");
    await waitFor(() => expect(state.refresh).toHaveBeenCalledWith({ silent: true }));
    expect(await screen.findByText("dashboard-page")).toBeInTheDocument();
  });

  it("a rate-limited switch shows the server's reason and stays put", async () => {
    const state = onboarded();
    mockUseAuth.mockReturnValue(state);
    mockSwitch.mockRejectedValue(
      new ApiError(429, "vertical switches are limited to one per user every 24 hours"),
    );
    renderSettings();

    await userEvent.click(await screen.findByRole("button", { name: /robotics/i }));
    await userEvent.click(screen.getByRole("button", { name: /switch vertical/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/one per user every 24 hours/i);
    // Still on settings, dialog still open so the button is a real retry.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByText("dashboard-page")).not.toBeInTheDocument();
    expect(state.refresh).not.toHaveBeenCalled();
  });

  it("the confirm copy promises the old vertical is kept, because the server keeps it", async () => {
    mockUseAuth.mockReturnValue(onboarded());
    renderSettings();

    await userEvent.click(await screen.findByRole("button", { name: /robotics/i }));

    const dialog = screen.getByRole("dialog");
    // The switch-back-is-quick claim rests on matches surviving on the deactivated profile row
    // (pinned server-side in test_profiles.py). If that ever stops being true, this copy lies.
    expect(dialog).toHaveTextContent(/nothing in energy & grid is deleted/i);
    expect(dialog).toHaveTextContent(/5 to 20 minutes/i);
  });
});
