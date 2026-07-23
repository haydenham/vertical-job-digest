import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, fetchVerticals, uploadResume, type Me } from "../api";
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

// What `refresh` resolves to once the freshly-uploaded profile is visible via /api/me.
const me = (vertical = "grid_power_software"): Me => ({
  user: { email: "a@b.co", name: "A", digest_paused: false },
  profile: { vertical, resume_version: "v1", backfill_status: "running" },
});

function auth(over: Partial<AuthState> = {}): AuthState {
  return {
    user: null,
    profile: null,
    loading: false,
    authError: false,
    refresh: vi.fn().mockResolvedValue(me()),
    logout: vi.fn(),
    ...over,
  };
}

const signedIn = (over: Partial<AuthState> = {}) =>
  auth({ user: { email: "a@b.co", name: "A", digest_paused: false }, ...over });

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
  afterEach(() => vi.useRealTimers());

  it("redirects to /login when not signed in", () => {
    mockUseAuth.mockReturnValue(auth({ user: null }));
    renderUpload();
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });

  it("discloses the AI-provider processing next to submit, linking the privacy notice", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    renderUpload();
    const disclosure = await screen.findByText(/processed by AI models/i);
    expect(disclosure).toHaveTextContent(/anthropic/i);
    expect(disclosure).toHaveTextContent(/openai/i);
    expect(screen.getByRole("link", { name: /privacy notice/i })).toHaveAttribute(
      "href",
      "/privacy",
    );
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
    mockUpload.mockResolvedValue({
      profile_id: 5,
      vertical: "aviation_software",
      resume_version: "v1",
    });
    renderUpload();
    await userEvent.click(await screen.findByRole("radio", { name: /aviation technology/i }));
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));
    expect(mockUpload).toHaveBeenCalledWith("aviation_software", resume);
  });

  it("in update mode locks the vertical (display name, no picker, no verticals fetch)", () => {
    mockUseAuth.mockReturnValue(
      signedIn({
        profile: { vertical: "aviation_software", resume_version: "v1", backfill_status: null },
      }),
    );
    renderUpload({ lockedVertical: "aviation_software" });
    expect(screen.getByText("Aviation Technology")).toBeInTheDocument();
    expect(screen.queryByText("aviation_software")).not.toBeInTheDocument();
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

  it("on success refreshes auth (silently) and routes to the dashboard", async () => {
    const refresh = vi.fn().mockResolvedValue(me());
    mockUseAuth.mockReturnValue(signedIn({ refresh }));
    mockUpload.mockResolvedValue({
      profile_id: 5,
      vertical: "grid_power_software",
      resume_version: "v3",
    });
    renderUpload();
    await screen.findByRole("radio", { name: /energy & grid/i });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));

    expect(await screen.findByText("dashboard-page")).toBeInTheDocument();
    expect(mockUpload).toHaveBeenCalledWith("grid_power_software", resume);
    // silent: the mid-form re-probe must not flip the global loading flag (the form would blank)
    expect(refresh).toHaveBeenCalledExactlyOnceWith({ silent: true });
  });

  it("retries a failed /api/me probe after a successful upload — never shows an error", async () => {
    const refresh = vi
      .fn()
      .mockRejectedValueOnce(new Error("transient 502"))
      .mockResolvedValue(me());
    mockUseAuth.mockReturnValue(signedIn({ refresh }));
    mockUpload.mockResolvedValue({
      profile_id: 5,
      vertical: "grid_power_software",
      resume_version: "v3",
    });
    renderUpload();
    await screen.findByRole("radio", { name: /energy & grid/i });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));

    // second probe attempt lands at +700ms and routes; no alert ever rendered
    expect(await screen.findByText("dashboard-page", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("falls back to 'open your dashboard' when the profile never confirms — not an error", async () => {
    vi.useFakeTimers();
    // upload succeeded, but /api/me keeps returning no profile (visibility race gone bad)
    const refresh = vi
      .fn()
      .mockResolvedValue({ user: { email: "a@b.co", name: "A", digest_paused: false }, profile: null });
    mockUseAuth.mockReturnValue(signedIn({ refresh }));
    mockUpload.mockResolvedValue({
      profile_id: 5,
      vertical: "grid_power_software",
      resume_version: "v3",
    });
    renderUpload();
    await act(() => vi.advanceTimersByTimeAsync(0)); // flush the verticals fetch
    fireEvent.change(screen.getByLabelText(/résumé/i), { target: { files: [resume] } });
    fireEvent.click(screen.getByRole("button", { name: /upload résumé/i }));

    await act(() => vi.advanceTimersByTimeAsync(0)); // POST resolves → finalizing
    expect(screen.getByText(/uploaded — loading your dashboard/i)).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(6_000)); // exhaust the bounded retries
    expect(screen.getByText(/your résumé is uploaded/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open your dashboard/i })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // never presented as a failure
  });

  it("shows a busy notice with spinner while the upload is in flight", async () => {
    vi.useFakeTimers();
    mockUseAuth.mockReturnValue(signedIn());
    mockUpload.mockImplementation(() => new Promise(() => {})); // hangs (bounded by the api timeout)
    renderUpload();
    await act(() => vi.advanceTimersByTimeAsync(0));
    fireEvent.change(screen.getByLabelText(/résumé/i), { target: { files: [resume] } });
    fireEvent.click(screen.getByRole("button", { name: /upload résumé/i }));

    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(screen.getByText(/uploading and starting your matches/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /uploading/i })).toBeDisabled();
  });

  it("maps a timed-out upload to a friendly error", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    mockUpload.mockRejectedValue(new DOMException("The operation was aborted.", "AbortError"));
    renderUpload();
    await screen.findByRole("radio", { name: /energy & grid/i });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/upload timed out/i);
  });

  it("maps a network failure to words, not a raw TypeError", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    mockUpload.mockRejectedValue(new TypeError("Failed to fetch"));
    renderUpload();
    await screen.findByRole("radio", { name: /energy & grid/i });
    await userEvent.upload(screen.getByLabelText(/résumé/i), resume);
    await userEvent.click(screen.getByRole("button", { name: /upload résumé/i }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't reach the server/i);
    expect(alert).not.toHaveTextContent(/TypeError/);
  });

  it("update mode has a back link to the dashboard", () => {
    mockUseAuth.mockReturnValue(
      signedIn({
        profile: { vertical: "aviation_software", resume_version: "v1", backfill_status: null },
      }),
    );
    renderUpload({ lockedVertical: "aviation_software" });
    expect(screen.getByRole("link", { name: /back to dashboard/i })).toHaveAttribute(
      "href",
      "/dashboard",
    );
  });

  it("onboarding mode has no back link (nowhere to go back to yet)", async () => {
    mockUseAuth.mockReturnValue(signedIn());
    renderUpload();
    await screen.findByRole("radio", { name: /energy & grid/i });
    expect(screen.queryByRole("link", { name: /back to dashboard/i })).not.toBeInTheDocument();
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
