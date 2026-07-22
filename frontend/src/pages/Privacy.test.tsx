import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Privacy } from "./Privacy";

// The privacy notice (compliance PR 1, D-094) is static — these pin the disclosures that matter
// (what's stored, the AI-provider processing, the contact path) without freezing every sentence.
describe("Privacy", () => {
  it("renders the notice with the key disclosure sections", () => {
    render(<Privacy />);
    expect(screen.getByRole("heading", { level: 1, name: /privacy notice/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /what rolefeed stores/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /how your résumé is used/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /deleting your data/i })).toBeInTheDocument();
  });

  it("discloses that résumé text is processed by Anthropic and OpenAI models", () => {
    render(<Privacy />);
    const disclosure = screen.getByText(/third-party AI model providers/i);
    expect(disclosure).toHaveTextContent(/anthropic/i);
    expect(disclosure).toHaveTextContent(/openai/i);
    expect(disclosure).toHaveTextContent(/not used to train/i);
  });

  it("links the contact email for unsubscribe and deletion requests", () => {
    render(<Privacy />);
    const links = screen.getAllByRole("link", { name: "haydenham10@gmail.com" });
    expect(links.length).toBeGreaterThanOrEqual(2);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "mailto:haydenham10@gmail.com");
    }
  });
});
