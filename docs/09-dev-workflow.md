# Development Workflow

*The standard software-engineering protocols this project runs by, beyond the testing levels in `08`. Same premise:
**Claude Code writes nearly all the code, so the human's leverage is the review gate and the automated gates, not the
typing.** These protocols exist to make AI-written code trustworthy: small reviewable diffs, machine-enforced quality
bars, and a definition of "done" that can't be skipped.*

## Definition of Done (a unit of work is not done until all hold)

1. **It does what was asked**, demonstrated by a test at the right pyramid level (`08`), passing locally.
2. **The default test suite is green** (`pytest`: unit + integration + system).
3. **Lint, format, and type-check pass** (see gates below).
4. **No secret, key, or DB file is in the diff** (`.env`/keys stay out — CLAUDE.md policy).
5. **The docs that the change touches are updated** — `WORKLOG.md` always (append, newest on top); `DECISIONS.md`
   if a re-litigable choice was made; the relevant `docs/04+` spec if an interface/schema moved.
6. **A human has read the diff.** Non-negotiable — see review gate.

"Mostly working, tests later" is not done. Because the author is a model, "later" has no owner.

## Branch & PR flow

- **Never commit straight to `main`.** Branch per unit of work: `feat/greenhouse-fetcher`, `fix/diff-empty-set`,
  `docs/testing-strategy`.
- **Small PRs.** One reviewable idea per PR — a fetcher, the diff job, the verification step. A 1,000-line PR of
  AI-generated code is unreviewable, and unreviewed AI code is the project's main risk. If a change sprawls, split it.
- **PR description states:** what changed, why, which `D-0xx` it implements/touches, and how it was tested.
- **`main` is always releasable** — i.e. the nightly pipeline can run off it. Broken `main` blocks the one thing
  that matters (the digest).
- **Once hosted, how a merged change actually ships** (data-only vs config/code redeploy, and the planned
  merge-triggered deploy) is spelled out in `docs/11` §5 "Post-launch change management".

## The review gate (the human's actual job here)

Because the code is model-written, **review is where correctness is decided, not where typos are caught.** Every PR:

1. **Automated review first:** run `/code-review` on the diff before a human looks — it triages the obvious before
   spending human attention.
2. **Human reads every line of the diff.** Not the description — the diff. Trust-but-verify is the whole operating
   model. Pay special attention to the contracts that cost trust if wrong: the diff's set arithmetic (D-016/D-009),
   the no-mass-close-on-failure guard, the verification gate (D-008), `content_hash` determinism, and anywhere an
   LLM output is consumed without validation.
3. **Question anything that "looks plausible."** Plausible-but-wrong is exactly the failure mode of generated code.
   If a test asserts something trivial, that's a red flag the behavior wasn't really pinned.

## Automated gates (CI + pre-commit — same checks, two moments)

Run identically as a **pre-commit hook** (fast feedback) and in **CI on every PR** (the enforced bar). A PR cannot
merge red.

| Gate | Tool | Bar |
|---|---|---|
| Format | `ruff format` | no diff |
| Lint | `ruff check` | clean |
| Types | `mypy` | clean; public functions typed |
| Tests | `pytest` (unit+integration+system) | green; `live`/`e2e` excluded (`08`) |
| Secrets | a secret-scan (e.g. `gitleaks`) | no findings |
| Lockfile | `uv lock --check` | lock in sync with `pyproject.toml` (D-014) |
| **Frontend** (path-filtered) | `npm run lint` + `typecheck` + `test` in `frontend/` | green — eslint + `tsc --noEmit` + vitest; pre-commit runs it only when `frontend/**.{ts,tsx}` is staged, CI as a parallel `frontend` job (D-042) |
| **LLM evals** (opt-in, metered) | `pytest -m eval` | extraction is manual/advisory (D-090); matching policy is decided in Block 4 |

Pre-commit mirrors CI so failures surface in seconds, not after a push. CI is the gate that can't be bypassed.

**The eval gate is conditional on purpose.** Evals hit the real configured provider, so an unconditional check
would tax a docs typo with tokens and flake risk. D-020 requires the gate only for prompt/matching/extraction
paths. The repository currently drifted from that policy: `ci.yml` has no eval job (D-090). Block 1 therefore
requires a documented manual parity run; Block 2 restores and expands the conditional job before any cutover.
Non-determinism is handled in the suite itself, not by weakening the target gate — see `08`.

## Conventions that keep generated code consistent

- **Commits:** imperative, scoped, reference the decision they implement where one exists —
  `feat(fetcher): add Lever module (D-018)`. Commit messages are the second narrative after `WORKLOG.md`.
- **Dependencies:** added only via `uv add`; the lockfile is committed; versions pinned (D-014). No stray `pip install`.
- **Config, not code (enforced):** the hard rule "nothing vertical-specific in code" (D-004) is a **review checklist
  item and ideally a test** — a grep/AST check that vertical names (`aviation`, `grid`, company slugs) never appear
  in `src/`, only in `config/` and `data/seed/`. The week-4 aviation add is the live exam (`06`).
- **Errors are loud, never swallowed:** fetchers raise `FetchError`; the pipeline records and alerts; every run
  writes `pipeline_runs` (`04` §7, `05`). A bare `except: pass` is a bug in review.
- **Structured logging** keyed by run id, employer, posting — so a failed night is debuggable from the log + the
  `pipeline_runs` row alone.

## Observability & cost as first-class (not "later")

- **Every pipeline run writes its summary** (`pipeline_runs`) including token usage and a best-effort
  `llm_cost_usd` catalog estimate (`NULL` when unavailable). Provider dashboards are authoritative for exact
  billing; local telemetry still makes token regressions visible the morning after. (D-005, D-090)
- **A failed/missing digest is itself the top-priority alert** (CLAUDE.md): the product is the digest landing; its
  absence must be loud.

## What this project deliberately does NOT do (yet)

Avoid ceremony that doesn't pay for a solo, pre-product build. Revisit when there are real users / a second developer:
- No multi-environment release trains, no staging cluster — local + (later) one VPS (D-012).
- No coverage-percentage gate (quality of asserts over quantity — `08`).
- No heavy branching model (no gitflow); short-lived branches off `main` is enough.
- No formal issue tracker required — `WORKLOG.md` "next/open threads" is the backlog until it hurts.

The non-negotiables above (tests at the right level, green gates, human-read diffs, updated docs) are the floor and
do not get traded away for speed — they are *what makes the speed safe* when a model is the one writing.
