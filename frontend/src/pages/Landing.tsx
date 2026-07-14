import { loginUrl } from "../api";

// Logged-out landing at `/` (D-065) — the Linear-style marketing page (UI rework PR 1, D-080).
// Static only: no endpoints, no state; the sole live element is the Google sign-in anchor. Copy
// decisions (coverage-led hero, section set, three-verticals-as-served) are Hayden's, recorded in
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
    title: "Software Engineer — Backend",
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
    <div className="hero-mock" aria-hidden="true">
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
      "and other specialized employers that broad job boards bury or miss.",
  },
  {
    title: "Apply while opportunities are fresh",
    body:
      "Start from newly opened roles, verified links, and a clear view of what has already closed " +
      "— so your time goes toward opportunities that are still real.",
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
];

export function Landing() {
  return (
    <div className="landing">
      <section className="hero">
        <h1 className="hero-title">The technology jobs the big boards miss.</h1>
        <p className="hero-sub">
          Rolefeed watches company career pages across aviation, energy, and robotics — surfacing
          overlooked technology roles and matching every new posting to your résumé, fresh each
          morning.
        </p>
        <div className="hero-actions">
          <a className="btn btn-primary" href={loginUrl()}>
            Sign in with Google
          </a>
          <a className="btn" href="#how-it-works">
            How it works
          </a>
        </div>
        <HeroMock />
      </section>

      <section className="stats" aria-label="Rolefeed in numbers">
        <div className="stat">
          <span className="stat-value">100+</span>
          <span className="stat-label">employers watched</span>
        </div>
        <div className="stat">
          <span className="stat-value">3</span>
          <span className="stat-label">verticals served</span>
        </div>
        <div className="stat">
          <span className="stat-value">daily</span>
          <span className="stat-label">every apply link verified</span>
        </div>
        <div className="stat">
          <span className="stat-value">90%</span>
          <span className="stat-label">of interviews go to first-day applicants — LinkedIn</span>
        </div>
      </section>

      <section className="pillars">
        {PILLARS.map((p) => (
          <div className="card" key={p.title}>
            <h3 className="card-title">{p.title}</h3>
            <p className="card-body">{p.body}</p>
          </div>
        ))}
      </section>

      <section className="how" id="how-it-works">
        <h2 className="section-title">How it works</h2>
        <ol className="steps">
          {STEPS.map((s, i) => (
            <li className="step" key={s.title}>
              <span className="step-num">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="card-title">{s.title}</h3>
              <p className="card-body">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="verticals">
        <h2 className="section-title">Built vertical by vertical</h2>
        <p className="section-sub">
          Deep coverage of a few industries beats shallow coverage of all of them.
        </p>
        <div className="vertical-cards">
          {VERTICALS.map((v) => (
            <div className="card" key={v.name}>
              <h3 className="card-title">{v.name}</h3>
              <p className="card-body">{v.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="founder">
        <h2 className="section-title">Why I built this</h2>
        <p className="founder-body">
          My name is Hayden, and I am a senior at the University of Wisconsin–Madison. I study
          computer science and economics, and the thought of entering the job market looms over my
          classmates and me. As an avid builder, I wanted to make a positive impact on the job
          search for myself and my peers, which inspired me to build Rolefeed. The three domains I
          chose reflect the general interests of my close peers and me, and they are often
          underserved on traditional job boards. Feel free to reach me at{" "}
          <a href="mailto:haydenham10@gmail.com">haydenham10@gmail.com</a> with any questions or
          inquiries.
        </p>
        <p className="founder-sig">— Hayden, founder</p>
      </section>

      <footer className="landing-footer">
        <div className="wordmark">
          <span className="mark" aria-hidden="true" />
          Rolefeed
        </div>
        <p className="footer-note">
          Rolefeed surfaces and reasons — it never auto-applies. Every application stays yours.
        </p>
        <p className="footer-copy">© 2026 Rolefeed</p>
      </footer>
    </div>
  );
}
