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

  it("points unsubscribe at the digest footer link (PR 2) with the email as fallback", () => {
    render(<Privacy />);
    expect(screen.getByText(/unsubscribe link in any digest/i)).toBeInTheDocument();
  });

  it("points pause and deletion at the self-serve settings page (PR 3)", () => {
    render(<Privacy />);
    const settingsLinks = screen.getAllByRole("link", { name: /settings page/i });
    expect(settingsLinks.length).toBe(2); // the email-pause section + the deletion section
    for (const link of settingsLinks) {
      expect(link).toHaveAttribute("href", "/settings");
    }
  });

  it("discloses that feedback lands in an inbox that account deletion does not reach (D-100)", () => {
    render(<Privacy />);
    expect(screen.getByText(/feedback you send/i)).toBeInTheDocument();
    expect(screen.getByText(/does not remove it from that inbox/i)).toBeInTheDocument();
  });

  it("links the contact email for unsubscribe and deletion requests", () => {
    render(<Privacy />);
    const links = screen.getAllByRole("link", { name: "haydenham10@gmail.com" });
    expect(links.length).toBeGreaterThanOrEqual(2);
    for (const link of links) {
      expect(link).toHaveAttribute("href", "mailto:haydenham10@gmail.com");
    }
  });

  it("carries no em dashes in its copy", () => {
    const { container } = render(<Privacy />);
    expect(container.textContent).not.toContain("—");
  });

  // A plain anchor, not a Router <Link> — this page renders for logged-out visitors and stays
  // Router-free, which is also why the test can render it without a MemoryRouter at all.
  it("offers a back link to the smart root without pulling in the router", () => {
    render(<Privacy />);
    expect(screen.getByRole("link", { name: /back/i })).toHaveAttribute("href", "/");
  });
});
