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
    title: "Beyond the usual suspects",
    body:
      "The same big-tech and finance roles flood every job board. Rolefeed covers the employers " +
      "the boards skip — airline tech arms, grid operators, robotics startups — with hundreds of " +
      "roles you won't find in any feed.",
  },
  {
    title: "Fresh postings, every day",
    body:
      "Jobs are pulled straight from company career pages nightly — often weeks before they " +
      "reach a board. A digest lands in your inbox each morning, and roles that vanish are " +
      "marked closed, so you never apply to a filled position.",
  },
  {
    title: "Brutally honest matching",
    body:
      "Every new role is matched against your résumé with a written verdict: what fits, what " +
      "doesn't, and a straight yes or no. It might sting — but you'll know where you stand " +
      "before you put your name out there.",
  },
];

const STEPS = [
  {
    title: "A bounded universe",
    body: "Each vertical starts from a curated list of the employers that matter in the space — total coverage of a real industry, not an infinite scrape.",
  },
  {
    title: "The nightly diff",
    body: "Rolefeed fetches every career page each night and diffs it against yesterday. New roles surface, vanished ones close, and every apply link is verified before it ships.",
  },
  {
    title: "A written verdict",
    body: "New postings are matched to your résumé with reasoning, not keyword similarity — fits, gaps, and a verdict that's willing to say no.",
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
        <h1 className="hero-title">The engineering jobs the big boards miss.</h1>
        <p className="hero-sub">
          Rolefeed watches company career pages across aerospace, energy, and robotics — the roles
          that never flood the LinkedIn feed — and matches every new posting to your résumé, fresh
          each morning.
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
          I'm a college senior recruiting for software roles. Hundreds of applications, few
          responses — the same big-tech jobs on every board, often weeks stale, with an ATS
          filtering my résumé before a human ever saw it. My classmates had the same experience.
          Rolefeed is the tool I wanted: the interesting jobs the boards miss, the morning they
          appear, with an honest read on my chances.
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
