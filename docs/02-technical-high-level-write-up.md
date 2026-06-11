**Vertical Job Intelligence Agent**

*Technical High-Level Write-Up*

Internal planning memo — Hayden Hamilton — June 2026

# 1. Architecture Overview

The system is a scheduled pipeline, not a live chat agent. Once a day it fetches the current state of every source in every configured vertical, diffs that state against the database, runs new and changed postings through LLM extraction and matching, verifies the results, and delivers a digest. The architecture is organized as three layers with sharply different cost and reliability profiles, and the central design rule is that the cheap deterministic path is always tried first, with LLM reasoning used only where structure runs out.

**Layer 1 — the ATS spine. **Deterministic fetchers against the public JSON endpoints of mainstream applicant tracking systems. Cheap, reliable, covers the majority of the employer universe, and works even when everything above it is broken.

**Layer 2 — LLM retrieval and extraction. **Probabilistic ingestion of unstructured sources: raw HTML careers pages, Hacker News Who’s Hiring threads, niche boards. Expensive per unit, robust to formatting chaos, and the layer that unlocks the long-tail inventory horizontal aggregators do not have.

**Layer 3 — agentic discovery. **A periodic agent whose job is not to find postings but to find sources: new employers for the universe. It expands the input to the layers below it.

A second design rule follows from the dual-vertical launch decision: nothing vertical-specific is hardcoded. A vertical is data — an employer list mapped to ATS types and endpoints, a list of niche sources, and a matching profile consisting of the resume plus a domain-vocabulary hint for the prompts. If adding the second vertical requires anything beyond configuration and curation, something has leaked into the code that should not be there.

# 2. Layer 1: The ATS Spine

Most target employers use one of a handful of ATS platforms, and several expose public JSON for their job boards. Greenhouse serves boards-api.greenhouse.io/v1/boards/{company}/jobs, Lever serves api.lever.co/v0/postings/{company}, and Ashby has a similar public posting endpoint. For these, the fetcher is an HTTP request and a JSON parse — no scraping, no rendering, no ambiguity. Each ATS type is implemented as a fetcher module behind a common interface, so an employer record is essentially a pointer to a fetcher plus an identifier.

Workday is the ugly tier and deserves its own note, because the biggest airlines and most utilities live there. Workday careers sites are JavaScript-heavy applications, but their internal API endpoints are discoverable and return JSON; the fetcher mimics those internal calls rather than rendering pages. These endpoints are undocumented and shift occasionally, so Workday fetchers are treated as higher-maintenance citizens with per-company configuration and loud failure alerts.

The diff job is the heart of the product. After each fetch cycle, the new snapshot is compared against stored state per employer: postings present now but not before are new; postings present before but absent now are marked closed rather than deleted. Death detection matters twice over — it keeps dead links out of the digest, and it accumulates a quietly valuable dataset, such as median posting lifespan per company, which tells the user how fast they need to apply. Deduplication handles the same role appearing on a careers page, LinkedIn, and a niche board: first-pass fuzzy matching on normalized title plus company plus location, with the LLM adjudicating ambiguous pairs during the extraction pass.

# 3. Layer 2: LLM Retrieval and Extraction

Every posting, regardless of source, is normalized by an extraction pass into a structured record: title, company, level, location and remote status, visa and work-authorization notes, technology stack, compensation if listed, posting date, and apply URL. For ATS-sourced postings this pass is mostly enrichment of already-structured data; for unstructured sources it is the whole ballgame. The canonical hard case is the twenty-five-person startup with a hand-edited careers page whose HTML changes whenever someone touches the site builder. Traditional scrapers die there because they depend on markup structure; an LLM reading the rendered text does not care. The fetcher hierarchy is therefore: JSON API if available, LLM-read-the-page as the universal fallback.

Unstructured sources beyond careers pages include the monthly Hacker News Who’s Hiring thread (a perfect extraction target: high signal, zero structure, and startups post there before anywhere else), niche vertical boards, and eventually newsletters. Cost discipline is enforced three ways. Extraction results are cached against a content hash, so an unchanged posting is never reprocessed. Models are tiered: a cheap model handles extraction, and the strongest model is reserved for matching rationale, where quality is visible to the user. And Layer 2 only runs on items the Layer 1 diff flags as new or changed — an agent loop that rereads forty careers pages daily with a frontier model is burning money to do what a diff does for free.

# 4. Layer 3: Agentic Discovery

The tool’s quality ceiling is set by the employer universe, and the universe is never finished: companies are founded, funded, renamed, and acquired. The discovery agent runs weekly, not daily, and is a genuine multi-step agent loop in the same architectural family as the flight disruption agent — search, navigate, verify, structure. Its sources are deliberately oblique: portfolio pages of aviation- and energy-focused venture investors, sponsor lists of industry conferences (a sponsor list is a lead list, not a job board), funding announcements, and competitors-of-X trails. For each candidate company it locates the careers page, identifies the ATS, probes for a JSON endpoint, and writes a proposed employer record. Proposals enter a review queue rather than the live universe; the schema anticipates this with a source field (manual versus agent-discovered) and a status field (proposed, approved, active, retired) on every employer. Human approval is the rule at first, with auto-approval considered only after the agent’s precision is measured.

# 5. The Matching Engine

Matching is reasoning, not similarity. For each new posting, the strongest model reads the structured posting and the user’s resume and writes an argument with three mandatory components: what fits, what does not fit, and a verdict. The willingness to state the negative case is a product requirement, not a style preference — a recommender that never says no is a recommender nobody trusts. Domain vocabulary from the vertical configuration steers the analysis (operations research, disruption management, and crew scheduling for aviation; power markets, dispatch optimization, and DER orchestration for grid software). A second, corpus-level pass looks across the recent window for patterns no per-posting analysis can see, such as a single company posting several related roles in a month, and surfaces them as hiring-trend notes in the digest.

Between matching and delivery sits verification, which exists because agentic ingestion fails weirdly: pages half-load, and a model can confidently extract a job from what is actually a customer testimonial. The minimum bar is that every apply link must resolve before a posting reaches the digest; postings failing verification are quarantined for inspection. One fake posting costs more trust than ten real ones earn.

# 6. Data Model and Delivery

Five core entities carry the system. **Employers** (vertical, name, ATS type, endpoint or careers URL, source, status, early-career volume estimate). **Sources** (non-employer feeds like the HN thread, typed by ingestion method). **Postings** (employer or source reference, raw payload, content hash, first-seen and last-seen timestamps, status of open or closed, plus the extracted structured fields). **Matches** (posting, profile, score, written rationale, verdict, model version). **Digests** (what was sent, when, and what it contained, so the system’s own behavior is auditable). Posting history is preserved rather than overwritten — the last-seen/first-seen pair is what makes both the diff and the lifespan statistics possible.

Delivery is a daily email digest first — new postings with rationale, closures, trend notes — because email meets the user where they already are and requires no frontend work. A small React dashboard follows for browsing, search, and the discovery-agent review queue. The dashboard is explicitly second: the digest is the product; the dashboard is furniture.

# 7. Stack and Build Sequence

Python throughout the pipeline, FastAPI for the eventual API surface, SQLite to start with a clean migration path to Postgres, the Anthropic SDK for all model calls, APScheduler or system cron for scheduling, and React for the later dashboard. Every component has a direct precedent in the flight disruption agent; the only genuinely new skills are scheduling and diffing, both small.

**Weeks one and two: **Layer 1 skeleton, aviation only. Employer table, Greenhouse/Lever/Ashby fetchers, postings table, the diff job, and a bare-bones daily email. No LLM yet. The first diff landing in the inbox is the proof-of-loop milestone.

**Week three: **LLM extraction and matching, including the negative-case rationale and the verification step.

**Week four: **Add the energy vertical. This week is the architecture test: it should cost a weekend of curation plus a configuration file, and any code change it forces is a defect to fix, not a feature to ship.

**Afterward: **Workday fetchers, the HN extraction source, the discovery agent, and the dashboard, in roughly that order of usefulness per unit effort.

# 8. Engineering Risks

Scraper rot is permanent weather: undocumented endpoints shift, and the system needs per-fetcher health checks with loud alerts rather than silent decay. Politeness matters — rate limiting, sane user agents, respect for robots.txt on the long tail — both ethically and because getting IP-banned from a careers site is a self-inflicted coverage hole. LLM costs are bounded by the cache-diff-tier discipline described above, but should be metered from day one so drift is visible. Hallucinated postings are handled by verification, but the subtler failure is extraction that is plausibly wrong — a misread location or level — which only spot-checking and user feedback catch. Finally, observability is not optional in a system that runs unattended at 6 a.m.: every pipeline run writes a summary record, and a digest that fails to send is itself an alert.

Page
# 9. Execution Model (Addendum — decided after the original write-up)

All fetching, credentials, and LLM calls live server-side in the nightly pipeline; users never trigger external calls and only read precomputed results from the database. This means spend is a function of postings per day rather than user activity, each ATS endpoint is hit once per day total regardless of user count, and the user-facing surface stays deliberately dumb — a digest email and later a read-only dashboard.

Matching is push, not pull. It runs as the final stage of the nightly pipeline, keyed on (new posting, active resume) pairs, because the digest email requires matching to be complete before delivery and login is an unreliable trigger. Real volume is new postings per day times users — a 40-employer vertical yields roughly 3 to 8 new postings daily — and a cheap deterministic pre-filter on level, location, and citizenship discards obvious non-matches before the strong model writes rationale.

Exactly three cases use an on-demand matching path, built separately: new-user backfill (resume versus all currently open postings, once, at signup), resume updates (re-match open postings; every match stores the resume_version it was computed against), and per-posting deep-dive analysis (a later, user-initiated, natural paid-tier feature). The matches table therefore carries resume_version and a trigger field (nightly, backfill, refresh) from day one, so the multi-user version is a feature rather than a refactor.

# 10. Delivery Surfaces (Addendum — decided)

Delivery is two surfaces over one dataset. The email digest remains the push channel: postings are time-sensitive, and the tool's output must arrive whether or not the user remembers the tool exists — a pull-only surface fails silently when the user simply stops visiting. The dashboard is the pull channel: a deliberately minimal single-page React table served by FastAPI as a read-only window onto the nightly-computed tables. Version one is exactly four columns — title, company, apply link, and match quality (verdict and score) — sorted newest first, refreshed once daily by the pipeline, with no live fetching and no logic of its own. Because the match-quality column depends on the matching engine, the dashboard ships at the end of week three alongside matching; everything beyond the four columns is post-week-four polish. The kill criterion applies to both surfaces equally: if the builder stops reading the digest and stops opening the dashboard by week three, the hypothesis is falsified.
