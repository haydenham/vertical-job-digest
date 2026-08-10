# Employer seed data

`employers_seed.csv` is the hand-curated starting universe of employers, one row per company.
It is the input to the Layer 1 ATS spine. Nothing vertical-specific lives in code — this file
(plus the vertical config) *is* the vertical.

## Workflow
1. **Hayden curates:** `name` + the priority/context columns (`tier`, `category`, `key_cities`, `role_tilt`).
2. **Claude resolves the ATS:** probes live Greenhouse/Lever/Ashby endpoints to mechanically *verify*
   `ats_type` + `ats_slug` where possible; otherwise fills a best-guess `ats_type` + `careers_url`.
   Every row carries a `verification` value (see below) so confidence is explicit.
3. **Hayden verifies** the `suspect` and `unverified` rows.
4. **Ground truth:** the Layer 1 fetcher loads each endpoint. A 404 or malformed response means the
   `ats_type`/`ats_slug` is wrong — fix and re-run. A structurally valid empty board is authoritative
   zero openings, though D-077 proposal activation still requires at least one validated job.
   Verification is ultimately mechanical, not manual.

## `verification` column — what each value means
| value | meaning | action needed |
|---|---|---|
| `verified` | ATS endpoint hit live and returned jobs / a valid API. | none — trust it |
| `detected` | Platform identified (from careers-page signature or search result URL), but the exact endpoint isn't live-confirmed yet. | confirm endpoint when building that fetcher |
| `layer2` | No clean API; routed to Layer 2 LLM-read-the-page. | none (handled by Layer 2) |

See `docs/07-ats-routing.md` for the full platform distribution and fetcher build priority.

## Columns
| column | who fills | values | notes |
|---|---|---|---|
| `vertical` | Hayden | `aviation_software` \| `grid_power_software` \| `robotics_software` \| `trading_software` | which vertical this employer belongs to. Rows are keyed on (`vertical`, `name`), so a company that is a genuine target in two universes may hold one row per vertical — see the trading section below (D-097) |
| `name` | Hayden | free text | company display name |
| `tier` | Hayden | `Tier 1`…`Tier 5` \| `Bonus` | priority signal; drives crawl ordering / volume estimates |
| `category` | Hayden | free text | e.g. Utility / IPP, Trading / Merchant, Quant Fund, Data SaaS |
| `key_cities` | Hayden | free text | US hubs; useful for the location pre-filter |
| `role_tilt` | Hayden | free text | tech flavor / what kind of roles to expect |
| `ats_type` | Claude | Layer-1 providers include `greenhouse`, `lever`, `ashby`, `workday`, `icims`, `workable`, `oracle_hcm`, `smartrecruiters`, `radancy`, `paylocity`, `phenom`, `bamboohr`, `pinpoint`, `rippling`; all values live in `vja.models.AtsType` | which fetcher (or Layer 2) handles this employer |
| `ats_slug` | Claude | free text | the company token in the ATS URL (e.g. Greenhouse `amperon`). For Workday: `tenant:dc:site` (e.g. `aes:wd1:AES_US`). Empty for portal-detected/custom rows. |
| `careers_url` | Claude | URL | the company's job board / careers page ("the job domain"). Required for `workday`/`raw_html`. |
| `endpoint` | derived | URL | constructed for slug-derived ATSs; explicit for Workday, Paylocity, and other per-tenant platforms. |
| `source` | default | `manual` \| `agent_discovered` | how the employer entered the universe. Seed rows are `manual`. |
| `status` | default | `proposed` \| `approved` \| `active` \| `retired` | seed rows default to `active`. |
| `verification` | Claude | `verified` \| `detected` \| `layer2` | confidence in the ATS resolution (see table above). |
| `notes` | optional | free text | anything useful (parent company, ATS quirks, why included). |

For Greenhouse/Lever/Ashby/Workable/SmartRecruiters/BambooHR/Pinpoint/Rippling the fetcher normally
**constructs** the endpoint from `ats_type` + `ats_slug`; an explicit endpoint overrides the derived URL
for provider-backed custom domains (Aurora's Pinpoint board) — the override is **Pinpoint-only**, so a
Rippling row's `endpoint` is ignored and its slug always wins. For Workday, Paylocity, and Phenom,
`endpoint` holds the per-tenant URL/config. Portal-detected and custom rows carry `careers_url`.

**Rippling rows:** the `ats_slug` is the board token in `ats.rippling.com/{slug}/jobs` (e.g.
`raptor-maps-inc`), not the company name. Rippling lists one row per (job × work location), so the
fetcher collapses them into one posting per job and joins the locations (D-096).

## Current seed status (grid/power vertical, 57 employers)
After the ATS-identification pass (see `docs/07-ats-routing.md`) + the P4.2 Workday + Phase-8
iCIMS/Workable/SmartRecruiters/Oracle/Radancy onboards:
- **37 verified**: Greenhouse (5), Lever (3), Ashby (3 — SPAN, WeaveGrid, **Base Power Company,
  curated 2026-08-08**), 15 Workday, **2 Workable (Vortexa, Energy
  Aspects — Phase 8)**, **4 iCIMS/Jibe (Constellation, Exelon, SIG, ICE — Phase 8)**,
  **1 SmartRecruiters (Vitol — Phase 8, D-050)**, **1 Oracle ORC (Southern Company — Phase 8, D-051)**,
  **1 Radancy/TalentBrew (NextEra — Phase 8, D-052)**, **1 Pinpoint (Aurora Energy Research —
  D-079)**, **1 Rippling (Camus Energy, moved off Greenhouse 2026-07-28 — D-096)**. All 37 are
  **fetchable today**.
- **8 detected** (platform known, no fetchable endpoint yet): Jobvite (2), SuccessFactors, Avature,
  UKG, Eightfold, **+2 Radancy parked (NRG, National Grid — generic fetcher exists but their
  search base isn't live-confirmed yet; onboard config-only once verified, D-052)**.
- **12 layer2** (no clean API → LLM-read): custom sites, incl. **Con Edison** (Oracle ORC but its
  host isn't exposed — curate canonical host+siteNumber to onboard).

**Deterministic ceiling ≈ 70%** of the universe via ~8 generic platform fetchers; ~30% routes to Layer 2.

## Current seed status (aviation vertical, 36 employers — Phase 7)
The Week-4 "vertical = config" add (D-002/D-004). Curated across all aviation sub-domains (airlines ·
avionics · OEM/manufacturers · GDS/airline-IT · flight-data/analytics · ATM/infrastructure ·
eVTOL/autonomy · travel-tech SaaS), ATS resolved by the same live-probing pass as grid:
- **15 verified** (live endpoint, fetchable today): Greenhouse (2 — OAG, FLYR), Lever (1 — Shield AI),
  Ashby (1 — Beacon AI), Workday (7 — Boeing, Airbus, Wisk Aero, **Sabre, Amadeus — Phase 8**, plus
  **Southwest and Thales — D-076**),
  **iCIMS/Jibe (2 — Garmin, SITA — Phase 8)**, **Phenom (1 — United, D-076)**, **Oracle ORC (1 —
  Honeywell, D-078: canonical host `ibqbjb.fa.ocs.oraclecloud.com` + `CX_1` found at the 2026-07-12
  coverage audit; 1,455 open at validation)**.
- **2 detected** (platform known, no fetchable endpoint yet): SuccessFactors (JetBlue), **L3Harris
  (Radancy parked — generic fetcher exists but its search base 301-redirects; onboard config-only
  once verified, D-052)**.
- **19 layer2** (no clean API → LLM-read): custom/JS-rendered sites in the flight-data, ATM, and
  remaining OEM/airline tail. Includes
  Collins/RTX (whole-conglomerate Workday board exceeds the ~4000 offset cap → Layer 2, D-046),
  **Alaska** (iCIMS *legacy* portal, no clean Jibe `/api/jobs` — re-confirmed at the 2026-07-12 audit),
  **Joby** (iCIMS legacy portal confirmed at the audit — no Jibe API), **Jeppesen (Boeing)** (duplicate
  coverage — its roles live on the already-fetched `Boeing` Workday board; retire candidate, D-078), and
  **Delta** (Avature: per-job JSON-LD but a 202 bot-challenge blocks server-side list fetch). Note: the
  Greenhouse `archer` board is a **name collision** (a veterinary clinic) — Archer Aviation is
  custom/Layer 2.

The big aerospace Workday boards are whole-company (Collins/RTX 4161, Airbus 2000, Boeing 1168, mostly
non-US/senior); the Stage-A scope gate + Stage-B US/level pre-filter cut this to the early-career US
software slice, same as grid's whole-company boards (GE Vernova etc.).

## Current seed status (robotics vertical, 30 employers — pre-beta)

Curated across humanoid/general robotics · embodied AI · warehouse/logistics · industrial/manufacturing ·
field/construction/agriculture/inspection · medical/service/consumer robotics. Existing aviation employers
remain owned by Aviation; the seed deliberately does not duplicate companies across verticals.

- **24 verified and fetchable today:** Greenhouse (10), Lever (5), Ashby (8), and Workday (1 — Boston
  Dynamics).
- **1 detected:** Universal Robots uses parent Teradyne's SAP SuccessFactors portal, for which there is no
  generic fetcher today.
- **5 Layer 2:** Symbotic, Intuitive Surgical, ABB Robotics, FANUC America, and iRobot. Their official career
  pages are retained without inventing an unsupported or unverified Layer-1 endpoint.

The initial deterministic coverage is **80% (24/30)**. Agent discovery is expected to propose the smaller
company tail later; it is not part of this curated starter set.

## Current seed status (trading vertical, 44 employers — D-097)

The fourth and (for now) last vertical, curated across market makers / prop trading · quant funds ·
exchanges & market infrastructure · trading technology · crypto & digital assets · prediction markets.
Scope is the shared one: US early-career software/data.

- **36 verified and fetchable today (82%):** Greenhouse (26), Ashby (4 — Voleon, Kraken, Kalshi,
  Polymarket), Workday (3 — CME Group, Nasdaq, Cboe), iCIMS/Jibe (2 — SIG, ICE), Lever (1 — Belvedere).
- **2 detected** (platform known, no generic fetcher): Two Sigma (Avature), Millennium (Eightfold).
- **6 layer2:** Citadel, Citadel Securities, D. E. Shaw, Bridgewater, Balyasny, Trading Technologies —
  custom or bot-blocked careers sites, retained without inventing an endpoint.

**Eight rows are deliberate cross-vertical duplicates (D-097):** Jane Street, Citadel, DRW,
SIG (Susquehanna), Millennium, Balyasny, CME Group, and ICE also exist under `grid_power_software`,
where they were curated for their *energy desks*. Because a user has exactly one vertical (D-064),
each universe carries its own row with identical ATS wiring — two `employer_id`s, two posting sets, two
independent diffs. Five of the eight are fetchable, so this costs **five extra nightly fetches** and a
duplicate extraction of the same bodies. The physical energy merchants (Shell, BP, Vitol, Trafigura,
Macquarie, Hartree, Freepoint, Castleton, Mercuria, Glencore, EDF Trading, Koch, Tenaska) stay
**grid-only** — power/gas trading is grid's thesis, not this vertical's.

Slug gotchas worth knowing before editing these rows: Optiver's US board is `optiverus` (plain `optiver`
is a near-empty global shell) · CTC is `chicagotrading` · Five Rings `fiveringsllc` · Headlands
`headlandstechnologiesllc` · MarketAxess `marketaxesscorporation` · Galaxy `galaxydigitalservices` ·
Kraken's Ashby slug is literally `kraken.com` · Radix splits campus (`radixuniversity`, in scope) from
experienced (`radixexperienced`) · Kalshi answers on both a stale Greenhouse board and Ashby — **Ashby is
pinned** · Cboe's public careers site is a Phenom front-end over its Workday tenant and **Workday is
pinned** · Hudson River Trading's only public API is its **campus/talent-community** Greenhouse board, so
two of its three entries are "join our talent community" placeholders that the Stage-A gate drops.
