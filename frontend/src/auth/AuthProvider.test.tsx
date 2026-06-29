import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMe, logout } from "../api";
import { AuthProvider } from "./AuthProvider";
import { useAuth } from "./useAuth";

vi.mock("../api", () => ({ fetchMe: vi.fn(), logout: vi.fn() }));

const mockFetchMe = vi.mocked(fetchMe);
const mockLogout = vi.mocked(logout);

function Probe() {
  const { user, loading } = useAuth();
  if (loading) return <span>loading</span>;
  return <span>{user ? user.email : "anon"}</span>;
}

function LogoutButton() {
  const { logout } = useAuth();
  return (
    <button type="button" onClick={() => void logout()}>
      out
    </button>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => vi.clearAllMocks());

  it("exposes the user once /api/me resolves", async () => {
    mockFetchMe.mockResolvedValue({ id: 1, email: "a@b.co", name: "A" });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(await screen.findByText("a@b.co")).toBeInTheDocument();
  });

  it("resolves to anonymous when /api/me returns null (401)", async () => {
    mockFetchMe.mockResolvedValue(null);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(await screen.findByText("anon")).toBeInTheDocument();
  });

  it("clears the user on logout", async () => {
    mockFetchMe.mockResolvedValue({ id: 1, email: "a@b.co", name: "A" });
    mockLogout.mockResolvedValue();
    render(
      <AuthProvider>
        <Probe />
        <LogoutButton />
      </AuthProvider>,
    );
    await screen.findByText("a@b.co");
    await userEvent.click(screen.getByRole("button", { name: "out" }));
    await waitFor(() => expect(screen.getByText("anon")).toBeInTheDocument());
    expect(mockLogout).toHaveBeenCalledOnce();
  });
});
