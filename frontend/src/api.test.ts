import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  fetchMe,
  loginUrl,
  postingsPath,
  uploadResume,
  type PostingsQuery,
} from "./api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

// The toggle → query-param mapping is the contract the dashboard rests on (the API pins the
// server side; this pins the client side). One home, unit-tested.
describe("postingsPath", () => {
  const base: PostingsQuery = {
    vertical: "grid_power_software",
    window: "all",
    view: "matched",
  };

  it("maps the default state to the matched / all-window query", () => {
    const params = new URLSearchParams(postingsPath(base).split("?")[1]);
    expect(params.get("vertical")).toBe("grid_power_software");
    expect(params.get("window")).toBe("all");
    expect(params.get("view")).toBe("matched");
    expect(params.has("profile_id")).toBe(false);
  });

  it("maps recency + view toggles to their params", () => {
    const params = new URLSearchParams(
      postingsPath({ ...base, window: "two_weeks", view: "cleaned" }).split("?")[1],
    );
    expect(params.get("window")).toBe("two_weeks");
    expect(params.get("view")).toBe("cleaned");
  });

  it("includes profile_id only when given", () => {
    const params = new URLSearchParams(postingsPath({ ...base, profileId: 7 }).split("?")[1]);
    expect(params.get("profile_id")).toBe("7");
  });
});

describe("loginUrl", () => {
  it("targets the API's /auth/login (API_BASE-prefixed)", () => {
    // API_BASE defaults to "" in tests (same-origin), so it's a bare path.
    expect(loginUrl()).toBe("/auth/login");
  });
});

describe("fetchMe", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("returns the user + their profile on 200", async () => {
    const me = {
      user: { email: "a@b.co", name: "A" },
      profile: { vertical: "grid_power_software", resume_version: "abc123" },
    };
    fetchMock.mockResolvedValue(jsonResponse(200, me));
    await expect(fetchMe()).resolves.toEqual(me);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/me",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("returns profile null when signed in but not onboarded", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { user: { email: "a@b.co", name: "A" }, profile: null }));
    await expect(fetchMe()).resolves.toEqual({ user: { email: "a@b.co", name: "A" }, profile: null });
  });

  it("treats 401 as logged-out (null), not an error", async () => {
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: "not authenticated" }));
    await expect(fetchMe()).resolves.toBeNull();
  });
});

describe("uploadResume", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
  });
  afterEach(() => vi.unstubAllGlobals());

  const file = new File(["résumé text"], "resume.txt", { type: "text/plain" });

  it("POSTs multipart credentialed and returns the created profile on 202", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(202, { profile_id: 5, vertical: "grid_power_software", resume_version: 3 }),
    );
    await expect(uploadResume("grid_power_software", file)).resolves.toEqual({
      profile_id: 5,
      vertical: "grid_power_software",
      resume_version: 3,
    });
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/profiles");
    expect(init).toMatchObject({ method: "POST", credentials: "include" });
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get("vertical")).toBe("grid_power_software");
  });

  it.each([
    [413, "file too large"],
    [422, "could not read résumé"],
    [429, "daily budget exceeded"],
    [401, "not authenticated"],
  ])("maps %i to an ApiError carrying the server detail", async (status, detail) => {
    fetchMock.mockResolvedValue(jsonResponse(status, { detail }));
    const err = await uploadResume("grid_power_software", file).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(status);
    expect((err as ApiError).message).toBe(detail);
  });
});
