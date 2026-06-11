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
| `verified` | ATS endpoint hit live and returned jobs / a valid API. | none — trust it |
| `detected` | Platform identified (from careers-page signature or search result URL), but the exact endpoint isn't live-confirmed yet. | confirm endpoint when building that fetcher |
| `layer2` | No clean API; routed to Layer 2 LLM-read-the-page. | none (handled by Layer 2) |

See `docs/07-ats-routing.md` for the full platform distribution and fetcher build priority.

## Columns
| column | who fills | values | notes |
|---|---|---|---|
| `vertical` | Hayden | `aviation_software` \| `grid_power_software` | which vertical this employer belongs to |
| `name` | Hayden | free text | company display name |
| `tier` | Hayden | `Tier 1`…`Tier 5` \| `Bonus` | priority signal; drives crawl ordering / volume estimates |
| `category` | Hayden | free text | e.g. Utility / IPP, Trading / Merchant, Quant Fund, Data SaaS |
| `key_cities` | Hayden | free text | US hubs; useful for the location pre-filter |
| `role_tilt` | Hayden | free text | tech flavor / what kind of roles to expect |
| `ats_type` | Claude | `greenhouse` \| `lever` \| `ashby` \| `workday` \| `icims` \| `workable` \| `oracle_hcm` \| `smartrecruiters` \| `jobvite` \| `successfactors` \| `avature` \| `ukg` \| `eightfold` \| `radancy` \| `custom` | which fetcher (or Layer 2) handles this employer |
| `ats_slug` | Claude | free text | the company token in the ATS URL (e.g. Greenhouse `amperon`). For Workday: `tenant:dc:site` (e.g. `aes:wd1:AES_US`). Empty for portal-detected/custom rows. |
| `careers_url` | Claude | URL | the company's job board / careers page ("the job domain"). Required for `workday`/`raw_html`. |
| `endpoint` | derived | URL | constructed in code from `ats_type` + `ats_slug` for GH/Lever/Ashby. Filled by hand for `workday`. |
| `source` | default | `manual` \| `agent_discovered` | how the employer entered the universe. Seed rows are `manual`. |
| `status` | default | `proposed` \| `approved` \| `active` \| `retired` | seed rows default to `active`. |
| `verification` | Claude | `verified` \| `detected` \| `layer2` | confidence in the ATS resolution (see table above). |
| `notes` | optional | free text | anything useful (parent company, ATS quirks, why included). |

For Greenhouse/Lever/Ashby/Workable the fetcher **constructs** the endpoint from `ats_type` + `ats_slug`.
For Workday, `endpoint` holds the full `cxs` jobs URL. Portal-detected (iCIMS/Oracle/etc.) and custom rows carry `careers_url`.

## Current seed status (grid/power vertical, 54 employers)
After the ATS-identification pass (see `docs/07-ats-routing.md`):
- **22 verified** (live endpoint): all Greenhouse (5), Lever (3), Ashby (1), 12 Workday, 1 Workable.
- **16 detected** (platform known, endpoint TBD): remaining Workday (3), iCIMS (4), Oracle HCM (2), SmartRecruiters, Jobvite, Workable, SuccessFactors, Avature, UKG, Eightfold.
- **16 layer2** (no clean API → LLM-read): 3 Radancy/Phenom portals + 13 custom sites.

**Deterministic ceiling ≈ 70%** of the universe via ~8 generic platform fetchers; ~30% routes to Layer 2.

Aviation vertical is not yet seeded.
