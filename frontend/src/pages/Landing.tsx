import { useRef, type CSSProperties } from "react";

import { loginUrl } from "../api";
import { useScrollReveal } from "../useScrollReveal";

// Stagger index for the shared reveal/hero keyframe (theme.css). Both the native scroll-driven
// path and the observer fallback read `--i`; the markup's only job is to number the items.
const step = (i: number) => ({ "--i": i }) as CSSProperties;

// Logged-out landing at `/` (D-065) — the Linear-style marketing page (UI rework PR 1, D-080).
// Static only: no endpoints, no state; the sole live element is the Google sign-in anchor. Copy
// decisions (coverage-led hero, section set, verticals-as-served) are Hayden's, recorded in
// docs/16. Renders inside the App shell, so the global header/nav stays above.

// The hero's product visual — a CSS-built miniature of the real dashboard on live v2 tokens
// (docs/16: no binary screenshot). Rows are illustrative, mirroring PostingsTable's markup.
const MOCK_ROWS: {
  company: string;
  title: string;
  location: string;
  date: string;
  verdict: "strong_yes" | "yes" | "maybe";
  label: string;
  score: number;
}[] = [
  {
    company: "flightaware",
    title: "Software Engineer, Backend",
    location: "Austin, TX",
    date: "2026-07-13",
    verdict: "strong_yes",
    label: "strong",
    score: 87,
  },
  {
    company: "ercot",
    title: "Grid Applications Developer",
    location: "Taylor, TX",
    date: "2026-07-13",
    verdict: "yes",
    label: "yes",
    score: 78,
  },
  {
    company: "tesla-energy",
    title: "Software Engineer, Autobidder",
    location: "Palo Alto, CA",
    date: "2026-07-12",
    verdict: "yes",
    label: "yes",
    score: 74,
  },
  {
    company: "united",
    title: "Associate Developer, Flight Ops",
    location: "Chicago, IL",
    date: "2026-07-12",
    verdict: "maybe",
    label: "maybe",
    score: 55,
  },
];

function HeroMock() {
  return (
    <div className="hero-mock" aria-hidden="true" style={step(3)}>
      <div className="hero-mock-bar">
        <span className="label">new today</span>
        <span className="hero-mock-count">4 new postings</span>
      </div>
      {MOCK_ROWS.map((r) => (
        <div className="hero-mock-row" key={r.company + r.title}>
          <span className="cell-company">{r.company}</span>
          <span className="cell-title">{r.title}</span>
          <span className="cell-location">{r.location}</span>
          <span className="cell-date">{r.date}</span>
          <span className="match">
            <span className={`verdict verdict-${r.verdict}`}>{r.label}</span>
            <span className={`score score-${r.verdict}`}>{r.score}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

const PILLARS = [
  {
    title: "Find roles beyond the obvious employers",
    body:
      "Explore technology opportunities at airline tech arms, grid operators, robotics startups, " +
      "trading firms, and other specialized employers that broad job boards bury or miss.",
  },
  {
    title: "Apply while opportunities are fresh",
    body:
      "Start from newly opened roles, verified links, and a clear view of what has already closed, " +
      "so your time goes toward opportunities that are still real.",
  },
  {
    title: "Know where you stand",
    body:
      "See what fits, what does not, and whether a role is worth your effort before you apply. " +
      "Honest recommendations help you focus without hiding the gaps.",
  },
];

const STEPS = [
  {
    title: "Curate the universe",
    body: "Rolefeed starts with a bounded, human-curated list of the employers that matter in each vertical rather than scraping an endless horizontal market.",
  },
  {
    title: "Fetch, diff, and verify",
    body: "Rolefeed fetches every career page each night and diffs it against yesterday. New roles surface, vanished ones close, and every apply link is verified before it ships.",
  },
  {
    title: "Extract, match, and deliver",
    body: "New roles are normalized, filtered to the vertical's scope, and matched to your résumé with written fits, gaps, and a verdict before they reach your dashboard and morning digest.",
  },
];

const VERTICALS = [
  {
    name: "Aviation Technology",
    body: "Airline ops and tech arms, flight data and tracking, avionics, and the platforms behind them.",
  },
  {
    name: "Energy & grid",
    body: "Grid operators, power-market software, storage and DER, nuclear, and utility innovation arms.",
  },
  {
    name: "Robotics",
    body: "Autonomy, industrial robotics, and the software that moves real machines.",
  },
  {
    name: "Trading & Markets",
    body: "Market makers and prop shops, quant funds, exchanges, and the low-latency systems they trade on.",
  },
];

export function Landing() {
  const pageRef = useRef<HTMLDivElement>(null);
  useScrollReveal(pageRef);

  return (
    <div className="landing" ref={pageRef}>
      {/* The hero animates on load (theme.css `.hero > *`), so it carries stagger indices but
          never the `reveal` class — it is above the fold and has no scroll position to arrive at. */}
      <section className="hero">
        <h1 className="hero-title" style={step(0)}>
          The technology jobs the big boards miss.
        </h1>
        <p className="hero-sub" style={step(1)}>
          Rolefeed watches company career pages across aviation, energy, robotics, and trading,
          surfacing overlooked technology roles and matching every new posting to your résumé, fresh
          each morning.
        </p>
        <div className="hero-actions" style={step(2)}>
          <a className="btn btn-primary" href={loginUrl()}>
            Sign in with Google
          </a>
          {/* Was the `#how-it-works` anchor. The demo board (D-105) is a stronger second CTA: the
              section it used to scroll to is still right there on the page, while this is the only
              way to see the actual roles without signing up first. A plain `<a>`, like every other
              link on this page — Landing stays router-free so it renders for a logged-out
              visitor (and in a bare test) with no context around it. */}
          <a className="btn" href="/demo">
            Browse live roles
          </a>
        </div>
        <HeroMock />
      </section>

      <section className="stats" aria-label="Rolefeed in numbers">
        <div className="stat reveal" style={step(0)}>
          <span className="stat-value">100+</span>
          <span className="stat-label">employers watched</span>
        </div>
        <div className="stat reveal" style={step(1)}>
          <span className="stat-value">4</span>
          <span className="stat-label">verticals served</span>
        </div>
        <div className="stat reveal" style={step(2)}>
          <span className="stat-value">daily</span>
          <span className="stat-label">every apply link verified</span>
        </div>
        <div className="stat reveal" style={step(3)}>
          <span className="stat-value">90%</span>
          <span className="stat-label">of interviews go to first-day applicants (LinkedIn)</span>
        </div>
      </section>

      <section className="pillars">
        {PILLARS.map((p, i) => (
          <div className="card reveal" key={p.title} style={step(i)}>
            <h3 className="card-title">{p.title}</h3>
            <p className="card-body">{p.body}</p>
          </div>
        ))}
      </section>

      {/* Heading and grid share one stagger sequence, so the block reads as a single arrival
          rather than two. Same shape in the verticals section below. */}
      <section className="how" id="how-it-works">
        <h2 className="section-title reveal" style={step(0)}>
          How it works
        </h2>
        <ol className="steps">
          {STEPS.map((s, i) => (
            <li className="step reveal" key={s.title} style={step(i + 1)}>
              <span className="step-num">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="card-title">{s.title}</h3>
              <p className="card-body">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="verticals">
        <h2 className="section-title reveal" style={step(0)}>
          Built vertical by vertical
        </h2>
        <p className="section-sub reveal" style={step(0)}>
          Deep coverage of a few industries beats shallow coverage of all of them.
        </p>
        <div className="vertical-cards">
          {VERTICALS.map((v, i) => (
            <div className="card reveal" key={v.name} style={step(i + 1)}>
              <h3 className="card-title">{v.name}</h3>
              <p className="card-body">{v.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="founder reveal">
        <h2 className="section-title">Why I built this</h2>
        <p className="founder-body">
          My name is Hayden, and I am a senior at the University of Wisconsin–Madison. I study
          computer science and economics, and the thought of entering the job market looms over my
          classmates and me. As an avid builder, I wanted to make a positive impact on the job
          search for myself and my peers, which inspired me to build Rolefeed. The four domains I
          chose reflect the general interests of my close peers and me, and they are often
          underserved on traditional job boards. Feel free to reach me at haydenham10 [at] gmail
          [dot] com with any questions or inquiries.
        </p>
        <p className="founder-sig">Hayden, founder</p>
      </section>

      <footer className="landing-footer reveal">
        <div className="wordmark">
          <span className="mark" aria-hidden="true" />
          Rolefeed
        </div>
        <p className="footer-note">
          Rolefeed surfaces and reasons. It never auto-applies, and every application stays yours.
        </p>
        <p className="footer-copy">
          © 2026 Rolefeed · <a href="/privacy">Privacy</a>
        </p>
      </footer>
    </div>
  );
}
