import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Login } from "./Login";

describe("Login", () => {
  it("renders a Google sign-in anchor to the API's /auth/login", () => {
    render(<Login />);
    const link = screen.getByRole("link", { name: /sign in with google/i });
    expect(link).toHaveAttribute("href", "/auth/login");
  });

  it("renders the auth card: heading + benefit lines", () => {
    render(<Login />);
    expect(screen.getByRole("heading", { name: /sign in to rolefeed/i })).toBeInTheDocument();
    expect(screen.getByText(/nightly digest of new roles/i)).toBeInTheDocument();
    expect(screen.getByText(/honest match verdicts/i)).toBeInTheDocument();
    expect(screen.getByText(/every apply link verified/i)).toBeInTheDocument();
  });

  it("no longer claims you can browse without signing in (stale since D-067)", () => {
    render(<Login />);
    expect(screen.queryByText(/without signing in/i)).not.toBeInTheDocument();
  });
});
