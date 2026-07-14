import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Landing } from "./Landing";

// The marketing landing (UI rework PR 1) is static — these pin the section skeleton and the one
// live element (the Google CTA), not the marketing copy itself.
describe("Landing", () => {
  it("renders the coverage-led hero with a Google sign-in anchor to /auth/login", () => {
    render(<Landing />);
    expect(
      screen.getByRole("heading", { level: 1, name: /engineering jobs the big boards miss/i }),
    ).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: /sign in with google/i });
    expect(cta).toHaveAttribute("href", "/auth/login");
  });

  it("renders the three thesis pillars", () => {
    render(<Landing />);
    expect(screen.getByRole("heading", { name: /beyond the usual suspects/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /fresh postings, every day/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /brutally honest matching/i })).toBeInTheDocument();
  });

  it("renders how-it-works as the anchor the hero's secondary CTA points at", () => {
    render(<Landing />);
    expect(screen.getByRole("link", { name: /how it works/i })).toHaveAttribute(
      "href",
      "#how-it-works",
    );
    expect(screen.getByRole("heading", { name: /^how it works$/i })).toBeInTheDocument();
  });

  it("renders the three served verticals", () => {
    render(<Landing />);
    expect(screen.getByRole("heading", { name: /aviation technology/i })).toBeInTheDocument();
    expect(screen.queryByText(/aerospace & aviation/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /energy & grid/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^robotics$/i })).toBeInTheDocument();
  });

  it("renders the founder story and the no-auto-apply footer", () => {
    render(<Landing />);
    expect(screen.getByRole("heading", { name: /why i built this/i })).toBeInTheDocument();
    expect(screen.getByText(/never auto-applies/i)).toBeInTheDocument();
  });
});
