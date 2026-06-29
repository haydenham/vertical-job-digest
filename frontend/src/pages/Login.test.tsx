import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Login } from "./Login";

describe("Login", () => {
  it("renders a Google sign-in anchor to the API's /auth/login", () => {
    render(<Login />);
    const link = screen.getByRole("link", { name: /sign in with google/i });
    expect(link).toHaveAttribute("href", "/auth/login");
  });
});
