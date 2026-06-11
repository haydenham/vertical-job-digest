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
4. **Ground truth:** the Layer 1 fetcher loads each endpoint. A 404/empty response means the
   `ats_type`/`ats_slug` is wrong — fix and re-run. Verification is ultimately mechanical, not manual.

## `verification` column — what each value means
| value | meaning | action needed |
|---|---|---|
| `verified` | ATS endpoint was hit live and returned a plausible job list (jobs > 0, right company). | none — trust it |
| `suspect` | A slug resolved, but the board looks wrong (0 jobs, or likely a different company sharing the name). | confirm the real ATS/slug |
| `unverified` | No ATS endpoint resolved by slug-probing; `ats_type`/`careers_url` are domain-knowledge best-guesses (mostly Workday/custom portals). | research + confirm |

## Columns
| column | who fills | values | notes |
|---|---|---|---|
| `vertical` | Hayden | `aviation_software` \| `grid_power_software` | which vertical this employer belongs to |
| `name` | Hayden | free text | company display name |
| `tier` | Hayden | `Tier 1`…`Tier 5` \| `Bonus` | priority signal; drives crawl ordering / volume estimates |
| `category` | Hayden | free text | e.g. Utility / IPP, Trading / Merchant, Quant Fund, Data SaaS |
| `key_cities` | Hayden | free text | US hubs; useful for the location pre-filter |
| `role_tilt` | Hayden | free text | tech flavor / what kind of roles to expect |
| `ats_type` | Claude | `greenhouse` \| `lever` \| `ashby` \| `workday` \| `raw_html` \| `unknown` | which fetcher handles this employer |
| `ats_slug` | Claude | free text | the company token in the ATS URL (e.g. Greenhouse `amperon`). Empty for `workday`/`raw_html`/`unknown`. |
| `careers_url` | Claude | URL | the company's job board / careers page ("the job domain"). Required for `workday`/`raw_html`. |
| `endpoint` | derived | URL | constructed in code from `ats_type` + `ats_slug` for GH/Lever/Ashby. Filled by hand for `workday`. |
| `source` | default | `manual` \| `agent_discovered` | how the employer entered the universe. Seed rows are `manual`. |
| `status` | default | `proposed` \| `approved` \| `active` \| `retired` | seed rows default to `active`. |
| `verification` | Claude | `verified` \| `suspect` \| `unverified` | confidence in the ATS resolution (see table above). |
| `notes` | optional | free text | anything useful (parent company, ATS quirks, why included). |

For Greenhouse/Lever/Ashby the fetcher **constructs** the endpoint from `ats_type` + `ats_slug`,
so those rows do not need a full URL. Only Workday and raw-HTML employers need `careers_url`/`endpoint`.

## Current seed status (grid/power vertical, 54 employers)
- **7 verified** (live ATS): Amperon, Arcadia, Camus Energy, Jane Street, Voltus, Yes Energy, WeaveGrid.
- **3 suspect** (slug resolved but board looks wrong): Constellation Energy, Koch Industries, Kraken (Octopus).
- **44 unverified** (Workday/custom guesses): the big utilities, banks, quant funds, exchanges, and a few startups.

Aviation vertical is not yet seeded.
