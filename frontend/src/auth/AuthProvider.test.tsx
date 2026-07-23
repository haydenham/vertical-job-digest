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
  const { user, profile, loading, authError } = useAuth();
  if (loading) return <span>loading</span>;
  if (authError) return <span>account-error</span>;
  if (!user) return <span>anon</span>;
  return <span>{`${user.email} / ${profile?.vertical ?? "no-profile"}`}</span>;
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

  it("exposes the user + their profile once /api/me resolves", async () => {
    mockFetchMe.mockResolvedValue({
      user: { email: "a@b.co", name: "A", digest_paused: false },
      profile: { vertical: "grid_power_software", resume_version: "v1", backfill_status: null },
    });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(await screen.findByText("a@b.co / grid_power_software")).toBeInTheDocument();
  });

  it("exposes profile as null when signed in but not onboarded", async () => {
    mockFetchMe.mockResolvedValue({ user: { email: "a@b.co", name: "A", digest_paused: false }, profile: null });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(await screen.findByText("a@b.co / no-profile")).toBeInTheDocument();
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

  it("keeps a non-401 /api/me failure distinct from logged-out", async () => {
    mockFetchMe.mockRejectedValue(new Error("500 Internal Server Error"));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(await screen.findByText("account-error")).toBeInTheDocument();
    expect(screen.queryByText("anon")).not.toBeInTheDocument();
  });

  it("silent refresh updates state without flipping the global loading flag", async () => {
    mockFetchMe.mockResolvedValueOnce({ user: { email: "a@b.co", name: "A", digest_paused: false }, profile: null });
    function SilentRefresh() {
      const { refresh } = useAuth();
      return (
        <button type="button" onClick={() => void refresh({ silent: true })}>
          silent
        </button>
      );
    }
    render(
      <AuthProvider>
        <Probe />
        <SilentRefresh />
      </AuthProvider>,
    );
    await screen.findByText("a@b.co / no-profile");

    // hold the re-probe open: the Probe must keep rendering the user, not "loading"
    let resolveMe!: (m: Awaited<ReturnType<typeof fetchMe>>) => void;
    mockFetchMe.mockImplementationOnce(() => new Promise((r) => (resolveMe = r)));
    await userEvent.click(screen.getByRole("button", { name: "silent" }));
    expect(screen.queryByText("loading")).not.toBeInTheDocument();

    resolveMe({
      user: { email: "a@b.co", name: "A", digest_paused: false },
      profile: { vertical: "grid_power_software", resume_version: "v2", backfill_status: null },
    });
    expect(await screen.findByText("a@b.co / grid_power_software")).toBeInTheDocument();
  });

  it("clears the user on logout", async () => {
    mockFetchMe.mockResolvedValue({
      user: { email: "a@b.co", name: "A", digest_paused: false },
      profile: null,
    });
    mockLogout.mockResolvedValue();
    render(
      <AuthProvider>
        <Probe />
        <LogoutButton />
      </AuthProvider>,
    );
    await screen.findByText(/a@b\.co/);
    await userEvent.click(screen.getByRole("button", { name: "out" }));
    await waitFor(() => expect(screen.getByText("anon")).toBeInTheDocument());
    expect(mockLogout).toHaveBeenCalledOnce();
  });
});
