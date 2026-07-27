import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Landing } from "./Landing";

// The marketing landing (UI rework PR 1, D-085 copy pass) is static — these pin the section
// responsibilities and live links without freezing every sentence of marketing copy.
describe("Landing", () => {
  it("promises overlooked technology jobs and links the Google CTA to /auth/login", () => {
    render(<Landing />);
    expect(
      screen.getByRole("heading", { level: 1, name: /technology jobs the big boards miss/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { level: 1, name: /engineering jobs/i }),
    ).not.toBeInTheDocument();
    const cta = screen.getByRole("link", { name: /sign in with google/i });
    expect(cta).toHaveAttribute("href", "/auth/login");
  });

  it("gives the three value cards distinct user-benefit jobs", () => {
    render(<Landing />);
    expect(
      screen.getByRole("heading", { name: /find roles beyond the obvious employers/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /apply while opportunities are fresh/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /know where you stand/i })).toBeInTheDocument();
  });

  it("renders how-it-works as the anchor the hero's secondary CTA points at", () => {
    render(<Landing />);
    expect(screen.getByRole("link", { name: /how it works/i })).toHaveAttribute(
      "href",
      "#how-it-works",
    );
    expect(screen.getByRole("heading", { name: /^how it works$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /curate the universe/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /fetch, diff, and verify/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /extract, match, and deliver/i })).toBeInTheDocument();
  });

  it("renders the four served verticals", () => {
    render(<Landing />);
    expect(screen.getByRole("heading", { name: /aviation technology/i })).toBeInTheDocument();
    expect(screen.queryByText(/aerospace & aviation/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /energy & grid/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^robotics$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /trading & markets/i })).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument(); // the stats band counts them
  });

  it("renders the founder story and the no-auto-apply footer", () => {
    render(<Landing />);
    expect(screen.getByRole("heading", { name: /why i built this/i })).toBeInTheDocument();
    expect(screen.getByText(/university of wisconsin.madison/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "haydenham10@gmail.com" })).toHaveAttribute(
      "href",
      "mailto:haydenham10@gmail.com",
    );
    expect(screen.getByText(/never auto-applies/i)).toBeInTheDocument();
  });

  it("links the privacy notice from the footer", () => {
    render(<Landing />);
    expect(screen.getByRole("link", { name: /privacy/i })).toHaveAttribute("href", "/privacy");
  });

  // Scroll motion: section blocks and card grids reveal on scroll, the hero does not — it is
  // above the fold and animates on load instead (theme.css `.hero > *`). Pinning the marker
  // classes keeps that split from drifting as sections are added.
  it("marks section blocks as scroll-reveal targets but never the hero", () => {
    const { container } = render(<Landing />);

    const hero = container.querySelector(".hero")!;
    expect(hero.querySelectorAll(".reveal")).toHaveLength(0);
    expect(hero.classList.contains("reveal")).toBe(false);

    // every below-the-fold block participates
    expect(container.querySelectorAll(".stats .reveal")).toHaveLength(4);
    expect(container.querySelectorAll(".pillars .reveal")).toHaveLength(3);
    expect(container.querySelectorAll(".how .reveal")).toHaveLength(4); // heading + 3 steps
    expect(container.querySelectorAll(".verticals .reveal")).toHaveLength(6); // heading + sub + 4
    expect(container.querySelector(".founder")).toHaveClass("reveal");
    expect(container.querySelector(".landing-footer")).toHaveClass("reveal");
  });

  it("staggers each grid within the cap, so the last card never arrives late", () => {
    const { container } = render(<Landing />);
    const indices = [...container.querySelectorAll<HTMLElement>(".reveal")].map((el) =>
      Number(el.style.getPropertyValue("--i")),
    );

    expect(indices.every((i) => Number.isInteger(i))).toBe(true);
    // --stagger is 70ms, so the budget of ~400ms tops out at index 5
    expect(Math.max(...indices)).toBeLessThanOrEqual(5);
  });
});
