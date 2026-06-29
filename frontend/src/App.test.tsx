import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { User } from "./api";
import { useAuth, type AuthState } from "./auth/useAuth";

// Stub the routed pages — App's job is the shell/nav/routing, not the pages' data flow.
vi.mock("./pages/Dashboard", () => ({ Dashboard: () => <div>dashboard-page</div> }));
vi.mock("./pages/Login", () => ({ Login: () => <div>login-page</div> }));
vi.mock("./pages/Upload", () => ({ Upload: () => <div>upload-page</div> }));
vi.mock("./auth/useAuth", () => ({ useAuth: vi.fn() }));

const mockUseAuth = vi.mocked(useAuth);
const logout = vi.fn();

function auth(over: Partial<AuthState> = {}): AuthState {
  return { user: null, loading: false, refresh: vi.fn(), logout, ...over };
}

const alice: User = { id: 1, email: "alice@example.com", name: "Alice" };

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App shell", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows a sign-in link to the API when logged out", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderAt("/");
    const link = screen.getByRole("link", { name: /sign in/i });
    expect(link).toHaveAttribute("href", "/auth/login");
    expect(screen.queryByText(/sign out/i)).not.toBeInTheDocument();
    expect(screen.getByText("dashboard-page")).toBeInTheDocument();
  });

  it("shows the email, upload link, and sign-out when logged in", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice }));
    renderAt("/");
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /upload résumé/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("calls logout when sign-out is clicked", async () => {
    mockUseAuth.mockReturnValue(auth({ user: alice }));
    renderAt("/");
    await userEvent.click(screen.getByRole("button", { name: /sign out/i }));
    expect(logout).toHaveBeenCalledOnce();
  });

  it("routes /upload to the upload page", () => {
    mockUseAuth.mockReturnValue(auth({ user: alice }));
    renderAt("/upload");
    expect(screen.getByText("upload-page")).toBeInTheDocument();
  });
});
