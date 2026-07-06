import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, fetchVerticals, uploadResume } from "../api";
import { useAuth, type AuthState } from "../auth/useAuth";
import { Upload } from "./Upload";

// Keep the real ApiError (the form branches on `instanceof`); mock only the network calls.
vi.mock("../api", async (importActual) => {
  const actual = await importActual<typeof import("../api")>();
  return { ...actual, fetchVerticals: vi.fn(), uploadResume: vi.fn() };
});
vi.mock("../auth/useAuth", () => ({ useAuth: vi.fn() }));

const mockVerticals = vi.mocked(fetchVerticals);
const mockUpload = vi.mocked(uploadResume);
const mockUseAuth = vi.mocked(useAuth);

function auth(over: Partial<AuthState> = {}): AuthState {
  return {
    user: null,
    profile: null,
    loading: false,
    refresh: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn(),
    ...over,
  };
}

const signedIn = (over: Partial<AuthState> = {}) =>
  auth({ user: { email: "a@b.co", name: "A" }, ...over });

function renderUpload(props: { lockedVertical?: string } = {}) {
  return render(
    <MemoryRouter initialEntries={["/upload"]}>
      <Routes>
        <Route path="/upload" element={<Upload {...props} />} />
        <Route path="/login" element={<div>login-page</div>} />
        <Route path="/dashboard" element={<div>dashboard-page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const resume = new File(["résumé text"], "resume.txt", { type: "text/plain" });

describe("Upload", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockVerticals.mockResolvedValue(["grid_power_software"]);
  });

  it("redirects to /login when not signed in", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderUpload();
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });

  it("renders the vertical picker + file input in onboarding mode", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    renderUpload();
    expect(await screen.findByRole("option", { name: "grid_power_software" })).toBeInTheDocument();
    expect(screen.getByLabelText(/résumé/i)).toBeInTheDocument();
  });

  it("in update mode locks the vertical (no picker, no verticals fetch)", () => {
    mockUseAuth.mockReturnValue(
      signedIn({ profile: { vertical: "aviation_software", resume_version: "v1" } }),
    );
    renderUpload({ lockedVertical: "aviation_software" });
    expect(screen.getByText("aviation_software")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(mockVerticals).not.toHaveBeenCalled();
  });

  it("on success refreshes auth and routes to the dashboard", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    mockUseAuth.mockReturnValue(signedIn({ refresh }));
    mockUpload.mockResolvedValue({
      profile_id: 5,
      vertical: "grid_power_software",
      resume_version: 3,
    });
    renderUpload();
    await screen.findByRole("option", { name: "grid_power_software" });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));

    expect(await screen.findByText("dashboard-page")).toBeInTheDocument();
    expect(mockUpload).toHaveBeenCalledWith("grid_power_software", resume);
    expect(refresh).toHaveBeenCalledOnce(); // new profile lands before the dashboard routes on it
  });

  it("surfaces the server message when the upload is rejected", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    mockUpload.mockRejectedValue(new ApiError(429, "daily budget exceeded"));
    renderUpload();
    await screen.findByRole("option", { name: "grid_power_software" });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));
    expect(await screen.findByText(/daily budget exceeded/i)).toBeInTheDocument();
  });
});
