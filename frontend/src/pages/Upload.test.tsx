import { fireEvent, render, screen } from "@testing-library/react";
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

  it("renders the vertical cards + file dropzone in onboarding mode", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    renderUpload();
    // slugs render as descriptive cards via verticalCopy, the first pre-selected
    const card = await screen.findByRole("radio", { name: /energy & grid/i });
    expect(card).toBeChecked();
    expect(screen.getByLabelText(/résumé/i)).toBeInTheDocument();
    expect(screen.getByText(/drop your résumé here/i)).toBeInTheDocument();
  });

  it("submits the vertical picked via its card", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    mockVerticals.mockResolvedValue(["grid_power_software", "aviation_software"]);
    mockUpload.mockResolvedValue({ profile_id: 5, vertical: "aviation_software", resume_version: 1 });
    renderUpload();
    await userEvent.click(await screen.findByRole("radio", { name: /aerospace & aviation/i }));
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));
    expect(mockUpload).toHaveBeenCalledWith("aviation_software", resume);
  });

  it("in update mode locks the vertical (display name, no picker, no verticals fetch)", () => {
    mockUseAuth.mockReturnValue(
      signedIn({ profile: { vertical: "aviation_software", resume_version: "v1" } }),
    );
    renderUpload({ lockedVertical: "aviation_software" });
    expect(screen.getByText("Aerospace & aviation")).toBeInTheDocument();
    expect(screen.getByText("aviation_software")).toBeInTheDocument(); // the slug, as data
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(mockVerticals).not.toHaveBeenCalled();
  });

  it("accepts a résumé dropped on the dropzone", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    renderUpload();
    await screen.findByRole("radio", { name: /energy & grid/i });
    fireEvent.drop(screen.getByText(/drop your résumé here/i), {
      dataTransfer: { files: [resume] },
    });
    expect(await screen.findByText("resume.txt")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upload résumé/i })).toBeEnabled();
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
    await screen.findByRole("radio", { name: /energy & grid/i });
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
    await screen.findByRole("radio", { name: /energy & grid/i });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/daily budget exceeded/i);
  });

  it("prefixes guard statuses with a friendly lead (409 second vertical)", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    mockUpload.mockRejectedValue(new ApiError(409, "profile already exists in grid_power_software"));
    renderUpload();
    await screen.findByRole("radio", { name: /energy & grid/i });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/already set up in another vertical/i);
    expect(alert).toHaveTextContent(/profile already exists/i); // server detail still shown
  });
});
