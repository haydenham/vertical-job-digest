# Vertical Config Spec

*Build spec for D-004 ("nothing vertical-specific in code"). This is the file the Week-4 energy add must prove:
spinning up a vertical = one config file + curated seed rows, zero code changes. Any forced code change is a defect.*

## What a vertical is, concretely

A vertical = four data inputs, all outside the code:
1. **Employer list** — rows in `data/seed/employers_seed.csv` filtered by the `vertical` column.
2. **Niche sources** — non-employer feeds (HN thread, niche boards) → `sources` table.
3. **Matching profile** — a resume + a domain vocabulary that steers the match prompt.
4. **Delivery + pre-filter knobs** — who gets the digest, and the cheap level/location/work-auth filter.

The pipeline iterates over configured verticals; it contains **no** `if vertical == "aviation"` branches.

## Directory layout

```
vertical-job-agent-starter/
  config/
    verticals/
      grid_power_software.yaml
      aviation_software.yaml        # not yet created
  data/
    seed/
      employers_seed.csv            # all verticals, one file, `vertical` column partitions it
  profiles/
    hayden_grid_resume.md           # referenced by a vertical's matching_profile
    hayden_aviation_resume.md
```

## Vertical config file format

`config/verticals/grid_power_software.yaml`:

```yaml
key: grid_power_software            # must match the `vertical` value in the seed CSV
display_name: "Grid / Power Software"

employer_seed:
  csv: data/seed/employers_seed.csv
  filter: { vertical: grid_power_software }   # which rows belong to this vertical

sources:                            # Layer 2 feeds (optional; can start empty)
  - kind: hn_whoishiring
    url: "https://news.ycombinator.com/item?id=<monthly-thread>"
    ingestion_method: llm_extract
  # - kind: niche_board
  #   url: ...

matching_profile:
  resume: profiles/hayden_grid_resume.md
  domain_vocabulary:                # steers the match prompt (Memo 02 §5)
    - power markets
    - dispatch optimization
    - DER orchestration
    - LMP / nodal pricing
    - demand response
    - battery / storage bidding
    - ISO/RTO operations

prefilter:                          # cheap deterministic gate before the strong model (D-006)
  locations: [US]
  levels: [intern, new_grad, early_career]
  # work_auth: ...

digest:
  recipients: ["haydenham10@gmail.com"]
  send_when: "after_pipeline"       # push at end of nightly run
```

## How the pipeline consumes it
- On startup, load every `config/verticals/*.yaml`.
- For each: import/refresh employers from the filtered seed CSV, register sources, load the matching profile into `profiles`.
- Nightly loop runs identically per vertical. Cost, diff, extraction, matching, digest are all vertical-agnostic; the
  config is the only thing that differs.

## The Week-4 test (D-002 / D-004)
Adding aviation must be exactly:
1. Add aviation rows to `employers_seed.csv` (curation + ATS probe).
2. Write `config/verticals/aviation_software.yaml`.
3. Add `profiles/hayden_aviation_resume.md`.

If step 4 ("…and change the code") appears, that's a defect to fix, not a feature to ship.
