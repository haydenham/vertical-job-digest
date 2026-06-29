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
  return { user: null, loading: false, refresh: vi.fn(), logout: vi.fn(), ...over };
}

function renderUpload() {
  return render(
    <MemoryRouter initialEntries={["/upload"]}>
      <Routes>
        <Route path="/upload" element={<Upload />} />
        <Route path="/login" element={<div>login-page</div>} />
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

  it("renders the vertical options and file input when signed in", async () => {
    mockUseAuth.mockReturnValue(auth({ user: { id: 1, email: "a@b.co", name: "A" } }));
    renderUpload();
    expect(await screen.findByRole("option", { name: "grid_power_software" })).toBeInTheDocument();
    expect(screen.getByLabelText(/résumé/i)).toBeInTheDocument();
  });

  it("uploads the file and shows the optimistic confirmation", async () => {
    mockUseAuth.mockReturnValue(auth({ user: { id: 1, email: "a@b.co", name: "A" } }));
    mockUpload.mockResolvedValue({
      profile_id: 5,
      vertical: "grid_power_software",
      resume_version: 3,
    });
    renderUpload();
    await screen.findByRole("option", { name: "grid_power_software" });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));
    expect(await screen.findByText(/résumé received \(v3\)/i)).toBeInTheDocument();
    expect(mockUpload).toHaveBeenCalledWith("grid_power_software", resume);
  });

  it("surfaces the server message when the upload is rejected", async () => {
    mockUseAuth.mockReturnValue(auth({ user: { id: 1, email: "a@b.co", name: "A" } }));
    mockUpload.mockRejectedValue(new ApiError(429, "daily budget exceeded"));
    renderUpload();
    await screen.findByRole("option", { name: "grid_power_software" });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));
    expect(await screen.findByText(/daily budget exceeded/i)).toBeInTheDocument();
  });
});
