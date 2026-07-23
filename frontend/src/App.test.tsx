import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { Profile, User } from "./api";
import { useAuth, type AuthState } from "./auth/useAuth";

// Stub the routed pages — App's job is the shell/nav/routing guards, not the pages' data flow.
vi.mock("./pages/Dashboard", () => ({ Dashboard: () => <div>dashboard-page</div> }));
vi.mock("./pages/Login", () => ({ Login: () => <div>login-page</div> }));
vi.mock("./pages/Upload", () => ({ Upload: () => <div>upload-page</div> }));
vi.mock("./pages/Landing", () => ({ Landing: () => <div>landing-page</div> }));
vi.mock("./pages/Privacy", () => ({ Privacy: () => <div>privacy-page</div> }));
vi.mock("./pages/Settings", () => ({ Settings: () => <div>settings-page</div> }));
vi.mock("./auth/useAuth", () => ({ useAuth: vi.fn() }));

const mockUseAuth = vi.mocked(useAuth);
const logout = vi.fn();

function auth(over: Partial<AuthState> = {}): AuthState {
  return {
    user: null,
    profile: null,
    loading: false,
    authError: false,
    refresh: vi.fn(),
    logout,
    ...over,
  };
}

const alice: User = { email: "alice@example.com", name: "Alice", digest_paused: false };
const gridProfile: Profile = {
  vertical: "grid_power_software",
  resume_version: "v1",
  backfill_status: null,
};

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App routing + guards", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  // --- nav chrome ---

  it("shows a sign-in link when logged out, and never renders the dashboard", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderAt("/");
    expect(screen.getByRole("link", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.queryByText(/sign out/i)).not.toBeInTheDocument();
    expect(screen.queryByText("dashboard-page")).not.toBeInTheDocument();
  });

  it("shows the email, update-résumé link, and sign-out when onboarded", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: gridProfile }));
    renderAt("/dashboard");
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /update résumé/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("shows the welcome tour once on the dashboard and persists dismissal", async () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: gridProfile }));
    const first = renderAt("/dashboard");
    expect(
      await screen.findByRole("dialog", { name: /your rolefeed, updated nightly/i }),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("rolefeed.tour.seen")).toBe("1");

    first.unmount();
    renderAt("/dashboard");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("reopens the welcome tour from the question-mark nav button", async () => {
    window.localStorage.setItem("rolefeed.tour.seen", "1");
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: gridProfile }));
    renderAt("/dashboard");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Open welcome tour" }));
    expect(
      screen.getByRole("dialog", { name: /your rolefeed, updated nightly/i }),
    ).toBeInTheDocument();
  });

  it("hides the update-résumé link when signed in but not onboarded", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: null }));
    renderAt("/onboarding");
    expect(screen.queryByRole("link", { name: /update résumé/i })).not.toBeInTheDocument();
  });

  it("shows the settings nav link for every signed-in user, even before onboarding", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: null }));
    renderAt("/onboarding");
    expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();
  });

  it("hides the settings nav link when logged out", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderAt("/");
    expect(screen.queryByRole("link", { name: /settings/i })).not.toBeInTheDocument();
  });

  it("calls logout when sign-out is clicked", async () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: gridProfile }));
    renderAt("/dashboard");
    await userEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(logout).toHaveBeenCalledOnce();
  });

  // --- the three root-routing branches (D-065) ---

  it("/ logged out → the landing page (not the dashboard)", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderAt("/");
    expect(screen.getByText("landing-page")).toBeInTheDocument();
  });

  it("/ signed in without a profile → onboarding", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: null }));
    renderAt("/");
    expect(screen.getByText("upload-page")).toBeInTheDocument();
  });

  it("/ signed in with a profile → the dashboard for their vertical", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: gridProfile }));
    renderAt("/");
    expect(screen.getByText("dashboard-page")).toBeInTheDocument();
  });

  // --- gated routes bounce correctly ---

  it("/dashboard logged out → login", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderAt("/dashboard");
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });

  it("/dashboard signed in without a profile → onboarding", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: null }));
    renderAt("/dashboard");
    expect(screen.getByText("upload-page")).toBeInTheDocument();
  });

  it("/onboarding when already onboarded → dashboard", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: gridProfile }));
    renderAt("/onboarding");
    expect(screen.getByText("dashboard-page")).toBeInTheDocument();
  });

  it("/login when already onboarded → dashboard", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: gridProfile }));
    renderAt("/login");
    expect(screen.getByText("dashboard-page")).toBeInTheDocument();
  });

  it("/login when signed in without a profile → onboarding", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: null }));
    renderAt("/login");
    expect(screen.getByText("upload-page")).toBeInTheDocument();
  });

  it("shows a retryable account error instead of the landing page when /api/me fails", async () => {
    const refresh = vi.fn().mockResolvedValue(null);
    mockUseAuth.mockReturnValue(auth({ authError: true, refresh }));
    renderAt("/");
    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't load your account/i);
    expect(screen.queryByText("landing-page")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(refresh).toHaveBeenCalledOnce();
  });

  it("shows a spinner while auth is loading", () => {
    mockUseAuth.mockReturnValue(auth({ loading: true }));
    renderAt("/");
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  // --- settings (compliance PR 3, D-094) ---

  it("/settings logged out → login", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderAt("/settings");
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });

  it("/settings renders for a signed-in user with no profile (deletion stays reachable)", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: null }));
    renderAt("/settings");
    expect(screen.getByText("settings-page")).toBeInTheDocument();
  });

  it("/settings renders for an onboarded user", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: gridProfile }));
    renderAt("/settings");
    expect(screen.getByText("settings-page")).toBeInTheDocument();
  });

  // --- privacy notice (compliance PR 1, D-094) ---

  it("/privacy is reachable logged-out, with the shell footer's privacy link", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderAt("/privacy");
    expect(screen.getByText("privacy-page")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^privacy$/i })).toHaveAttribute("href", "/privacy");
  });

  it("/privacy is reachable while signed in", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice, profile: gridProfile }));
    renderAt("/privacy");
    expect(screen.getByText("privacy-page")).toBeInTheDocument();
  });

  it("the shell footer stays off the root route, where the landing owns the footer", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderAt("/");
    expect(screen.getByText("landing-page")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^privacy$/i })).not.toBeInTheDocument();
  });
});
