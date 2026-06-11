**Vertical Job Intelligence Agent**

*Business Concept White Paper — honest internal memo, risks included*

Internal planning memo — Hayden Hamilton — June 2026

# 1. The Problem

Horizontal job aggregators are optimized for breadth and recency at massive scale, and that optimization makes them structurally bad at two things: niche coverage and depth of matching. LinkedIn, Indeed, and Google Jobs index what is pushed to them or what their crawlers prioritize, and their matching is keyword- and embedding-based, which produces the familiar wall of irrelevant recommendations. For a job seeker targeting a specific industry rather than a specific title, the experience is worse still: the best roles in a niche vertical are scattered across dozens of company careers pages, a handful of obscure boards, monthly Hacker News threads, and small-company websites with no applicant tracking system at all. Many of the most interesting roles never surface prominently on the big boards, and the ones that do are buried under noise.

The seekers who feel this pain most acutely are people who want into an industry, not just into a job. They will check the same fifteen careers pages by hand every week. They are passionate, underserved, and concentrated in identifiable communities. That combination — fragmented inventory, motivated users, and an incumbent that is structurally incapable of serving them well — is the opening.

# 2. The Product

The product is a vertical job intelligence agent: a tool that achieves effectively total coverage of a small, bounded employer universe within one niche industry, and delivers a daily digest of what changed, with reasoned matching against the user’s actual background. The core loop is simple. Every day the system fetches all postings from every employer in the vertical, diffs them against yesterday’s state, runs new postings through an LLM extraction and matching pass, and delivers a short digest: what appeared, what closed, and for each new posting, a written argument for or against applying.

Three properties separate this from existing tools. First, total coverage: the universe per vertical is thirty to fifty employers, small enough that complete daily coverage is achievable, including small companies with raw HTML careers pages that no traditional aggregator can parse. Second, the diff is the product: the user is never shown a stale wall of listings, only what is new since yesterday, which is the question a serious job seeker actually has. Third, matching with reasoning: instead of a similarity score, the system writes an argument — what fits, what does not fit, and a verdict — and its willingness to say no is what builds trust. A fourth, longer-term property is corpus-level pattern detection: noticing that a particular company has posted three operations-technology roles in a month and surfacing that as a hiring-trend signal no keyword board can produce.

# 3. Why Vertical, Not Horizontal

The generic version of this pitch — find interesting jobs tailored to your resume — is crowded. Hiring Cafe aggregates directly from company ATS pages and has a devoted following precisely because it skips LinkedIn’s spam. Simplify does resume matching and application autofill for new grads. Otta built a company on curated, matched tech roles. LinkedIn itself has alerts, and their badness is the reason these companies exist, but it means the horizontal lane is contested by funded players with distribution. Competing there means losing on coverage to Hiring Cafe and on distribution to LinkedIn simultaneously.

The vertical version competes with nobody. “Every aviation software job in America, including the ones at forty-person companies you have never heard of, matched against your background with reasoning” is a product no one offers, because each vertical is too small for a venture-backed company to care about and too fragmented for a horizontal player to surface well. This is the bowling-pin strategy: knock down one pin completely rather than grazing ten. The historical pattern is well established — Craigslist was unbundled vertical by vertical, and a small group of users who feel completely served will evangelize, while a large group who feel generically served will churn. Defensibility in this model does not come from technology, which is replicable, but from curation (the employer universe is hand-built and continuously maintained), from coverage of the no-ATS long tail that is uneconomical for incumbents, and from trust earned by match quality in front of a small, dense audience.

# 4. Launch Verticals: Aviation Software and Grid/Power Software

The first vertical is aviation software: airline operations and technology arms (United, Delta, JetBlue, Southwest, Alaska), platform companies (Sabre, Amadeus, Navitaire), data and tracking companies (FlightAware, Cirium, Flightradar24), and revenue and operations startups (FLYR, Volantio, plus cargo and airport-ops software). Scope is deliberately narrow at launch: early-career software and data roles, United States. The universe is crisp-edged and arguably the most bounded of any candidate vertical, nobody aggregates it, and the founder is the literal target user — actively recruiting into this industry over the next year, with the domain knowledge to judge match quality on sight.

The second vertical is grid and power software: the ISOs and RTOs themselves (ERCOT, CAISO, PJM hire software engineers directly, which almost nobody knows), grid software companies (Camus, GridStatus, Arcadia), storage and DER optimization (Tesla Energy, Fluence), power trading and analytics shops, nuclear-revival companies, and utility innovation arms. This is the aviation-shaped corner of energy — deliberately not “climate tech,” where Climatebase already serves the market and the universe is hundreds of fast-dying startups. Grid software has genuine market momentum (electrification, data-center power demand, nuclear revival), excellent community watering holes, and a seeker profile — quantitative CS-and-economics people — that matches the founder exactly. The founder is also genuinely recruiting into this vertical, so the dogfooding loop holds in both markets.

Launching two verticals simultaneously is not scope creep; it is the cheapest possible proof of the expansion thesis. Because the architecture treats a vertical as configuration rather than code, the second vertical costs roughly a weekend of employer-list curation. If it costs more than that, the architecture has failed a test worth failing early.

# 5. The Expansion Playbook

If the product instinct proves out, growth is vertical replication, not horizontal generalization. The product becomes a machine whose input is a vertical definition — an employer list mapped to ATS endpoints, a set of niche sources, and a domain vocabulary for the matching prompts — and whose output is a new instance. Vertical selection criteria are now explicit, derived from what makes the launch verticals good: a bounded employer universe of dozens rather than thousands; seekers underserved by LinkedIn’s relevance ranking; employers concentrated on API-friendly ATS platforms; a community watering hole that doubles as a zero-cost distribution channel; and passionate seekers who want into the industry specifically. Leading candidates for vertical three include defense tech and dual-use startups (booming, bounded, fashionable among new grads, heavy Greenhouse and Lever usage), sports analytics (passionate audience, though TeamWork Online partially serves it), and maritime tech (genuinely uncovered inventory, but a thin and scattered seeker community — great supply, unclear demand). Each new vertical multiplies maintenance surface, so expansion is gated on two proofs from existing verticals: the pipeline runs itself with minimal babysitting, and real users retain. Expansion before retention is how this becomes three half-dead verticals instead of one alive one.

# 6. Monetization (Exploratory, Not Committed)

Monetization is miles away and explicitly not a near-term goal, but the cost structure suggests a natural shape. The deterministic ATS layer costs pennies to run and could anchor a free tier: the daily digest for one vertical. The LLM-powered layers — extraction from unstructured sources, reasoned matching against an uploaded resume, and agentic discovery of long-tail employers — are where marginal cost per user actually lives, and they map cleanly onto a paid tier. This alignment between price and cost is accidental but real. Plausible price anchors for niche job tools run ten to twenty dollars a month for active seekers, but willingness to pay is an open question documented in the companion future-questions memo. The honest framing: this is a free option on a product, sitting on top of a tool that justifies itself even if the option expires worthless.

# 7. Risks, Stated Plainly

**Tiny addressable market per vertical. **Aviation software early-career seekers in the US number in the low thousands at most. The business case depends entirely on the replication playbook working across many verticals, and that is unproven.

**Maintenance burden compounds. **ATS endpoints change, scrapers rot, small-company careers pages disappear. Every vertical added is a standing maintenance obligation owned, for now, by one student with a degree to finish.

**Legal and terms-of-service gray areas. **The ATS JSON endpoints are public but mostly undocumented; long-tail page reading is scraping in the plain sense. As a personal tool this is benign; as a commercial product it requires a real legal posture, and aggregator startups have died on this hill before.

**Incumbents can copy the visible features. **Reasoned matching is a prompt away for Hiring Cafe or LinkedIn. The defensible parts are curation and trust, which are slow to build and easy to underestimate.

**Distribution is unsolved. **Watering-hole communities are a hypothesis, not a channel. Niche audiences are reachable but small, and posting a tool into a subreddit once is not a growth strategy.

**Trust is asymmetric. **One hallucinated or dead posting costs more credibility than ten good matches earn. Verification machinery is not optional.

**Founder concentration risk. **The builder is also the user, the curator, and the maintainer, while interning, finishing a degree, and recruiting. The realistic failure mode is not competition; it is abandonment in week five.

# 8. Win Conditions and Kill Criteria

This project is structured so that the floor is high. Even if no business ever materializes, the tool is a portfolio piece demonstrating agentic architecture, a daily-use instrument during two recruiting seasons, and an interview story (“I built the agent that found this job posting”). The win condition for the tool is simple: it surfaces at least one role per vertical that the founder applies to and would not otherwise have found, and the founder is still reading his own digest after six weeks. The kill criterion is equally simple and should be honored without sentiment: if the founder stops reading his own digest by week three, the product hypothesis is falsified at a cost of one month, which is the cheapest possible price for that information. The business question — whether anyone else will use it, retain, and pay — is deferred until the personal version has survived contact with its first and most motivated user.

Page