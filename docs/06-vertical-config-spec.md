# Vertical Config Spec

*Build spec for D-004 ("nothing vertical-specific in code"). Aviation proved the architecture test first;
Robotics repeats it: spinning up a vertical = one config file + curated seed rows + a matching profile, zero
application-code changes. Any forced application-code change is a defect.*

## What a vertical is, concretely

A vertical = four data inputs, all outside the code:
1. **Employer list** — rows in `data/seed/employers_seed.csv` filtered by the `vertical` column.
2. **Niche sources** — non-employer feeds (HN thread, niche boards) → `sources` table.
3. **Matching profile** — a resume + a domain vocabulary that steers the match prompt.
4. **Delivery + pre-filter knobs** — who gets the digest, and the cheap level/location/work-auth filter.

The pipeline iterates over configured verticals; it contains **no** per-vertical branches.

## Directory layout

```
vertical-job-agent-starter/
  config/
    verticals/
      grid_power_software.yaml
      aviation_software.yaml
      robotics_software.yaml
      profiles/
        hayden_grid_resume.md
        hayden_aviation_resume.md
        hayden_robotics_resume.md
  data/
    seed/
      employers_seed.csv            # all verticals, one file, `vertical` column partitions it
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
  user_email: haydenham10@gmail.com # whose resume this is (the profile key, with `key`)
  resume: profiles/hayden_grid_resume.md
  domain_vocabulary:                # steers the match prompt (Memo 02 §5)
    - power markets
    - dispatch optimization
    - DER orchestration
    - LMP / nodal pricing
    - demand response
    - battery / storage bidding
    - ISO/RTO operations

scope:                              # Stage-A free title gate (D-023, P5.1) — resume-independent
  role_include: [software, engineer, developer, data, analyst, scientist, machine learning]
  exclude: [senior, sr, staff, principal, lead, manager, director, vp, technician, sales]
  # Keep a title iff it matches a role_include keyword AND no exclude keyword
  # (whole-word, case-insensitive). Coarse on purpose; Stage B + the LLM refine. Tune freely.

prefilter:                          # Stage-B cheap deterministic gate, post-extraction (D-023, P5.3)
  locations: [US]                    # keep US/remote/unknown; drop clearly-foreign extracted locations
  levels: [intern, new_grad, early_career]   # drop a *confirmed* level outside this set; unknown passes
  # Consumed by src/vja/prefilter.py to decide which Stage-A survivors earn the strong match model.
  # Coarse on purpose (the LLM refines); work_auth is surfaced to the matcher, not gated here (D-036).

digest:
  recipients: ["haydenham10@gmail.com"]
  send_when: "after_pipeline"       # push at end of nightly run
```

## How the pipeline consumes it
- On startup, load every `config/verticals/*.yaml`.
- For each: import/refresh employers from the filtered seed CSV, register sources, load the matching profile into `profiles`.
- Nightly loop runs identically per vertical. Cost, diff, extraction, matching, digest are all vertical-agnostic; the
  config is the only thing that differs.

## The vertical-add test (D-002 / D-004)
Adding a vertical must be exactly:
1. Add its rows to `employers_seed.csv` (curation + ATS probe).
2. Write `config/verticals/<key>.yaml`.
3. Add the matching profile referenced by that YAML under `config/verticals/profiles/`.

Application-code changes are a defect to fix, not part of adding a vertical. Tests and documentation should
still pin the newly configured input.
