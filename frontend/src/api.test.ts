import { describe, expect, it } from "vitest";

import { postingsPath, type PostingsQuery } from "./api";

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
