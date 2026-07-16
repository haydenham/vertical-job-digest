# LLM cost optimization — plan of record (D-090)

*Working execution plan accepted by Hayden on 2026-07-16. Read
`docs/INVARIANTS.md` → `WORKLOG.md` top → this file to continue after a reset. Every block is a
separate branch/review decision; Hayden commits and opens PRs.*

## Outcome and sequencing

Rolefeed must be able to evaluate and change extraction/matching models without provider SDK code
changes, then choose both models from measured quality, latency, and catalog cost. This work is a
beta/Robotics prerequisite, but it must not erase the production evidence from D-088/D-089.

1. **Block 0 — observe (ACTIVE):** July 17 is D-088 production observation night 1 (July 16 began before
   #88 merged). Compare employer-level churn, stage tokens, cost, failures, and runtime before
   attributing savings to any model change. July 18 remains observation night 2.
2. **Block 1 — provider boundary (COMPLETE):** embedded LiteLLM preserves the current Anthropic
   models and behavior and replaces provider-specific types/rates with a typed local contract.
   Merged as PR #90 and deployed as image `07ed265` on 2026-07-16.
3. **Block 2 — evaluation harness (new-model step 1/3):** expand the small synthetic extraction/matching set, collect
   quality/latency/token/catalog-cost evidence across candidate models, and restore the missing
   path-filtered eval CI job documented by D-020/D-021.
4. **Block 3 — extraction cutover (new-model step 2/3):** choose and deploy the lowest-cost extraction model that clears
   the accepted extraction threshold. DeepSeek is a candidate, not a decision.
5. **Block 4 — matching cutover (new-model step 3/3):** choose and deploy the best value matching model that clears the
   trust threshold. Sonnet, Grok, Muse, and the proposed GPT route are candidates, not decisions;
   exact available model identifiers and prices are verified in Block 2.
6. **Block 5 — NO-output optimization (separate follow-on):** against the chosen matching model, test and implement the
   approved contract that a `no` verdict stores no user-facing reasoning fields, if the eval shows
   the shorter schema/prompt preserves rejection quality and produces material output-token savings.

No candidate wins from a benchmark headline or vendor claim. Extraction and matching are separate
choices because their quality/cost requirements differ.

Put differently: **three steps remain for testing/selecting new models** (evaluation harness → extraction
choice → matching choice). The `no`-output work is a fourth, separate optimization performed only after the
matching model is selected.

## Immediate handoff — observe before changing anything

Do not merge/deploy another model, prompt, provider, seed, fetcher, or environment change before reviewing the
July 17 run. The read-only morning audit covers four recently landed behaviors together:

1. **D-088 snapshot integrity:** employer-level fetched/new/reopened/updated/closed/unchanged counts; total-drift,
   exact-count, duplicate-ID, and recurring GE Vernova failures. Keep production frozen through July 18 when
   practical so the promised second observation night remains comparable.
2. **D-089 score normalization:** clamp-warning count and values; no remaining out-of-range validation failures;
   repaired matches persist and do not return as paid retries.
3. **D-090 LiteLLM:** actual upstream model IDs remain Haiku 4.5/Sonnet 4.6; no unsupported-parameter, parsing,
   missing-usage/pricing, or false-zero errors; input/output/cache buckets and catalog cost look plausible against
   the prior Anthropic baseline.
4. **D-086 operations:** one scheduled execution/attempt, completion within six hours, expected digest delivery,
   and no duplicates. Reconfirm service health and anonymous-postings `401`.

Block 2 starts only after Hayden reviews that evidence and approves its fixtures, rubric, pass thresholds,
candidate list, repetition count, and maximum eval spend.

## Block 1 — LiteLLM provider boundary

### Accepted scope

- Use the **embedded LiteLLM Python SDK**, not a proxy service.
- `vja.llm` is the only LiteLLM-facing module. Extraction, matching, and nightly orchestration use
  its typed `StructuredLLM`/`StructuredResult` contract; LiteLLM response types do not leak upward.
- Model routes are call-time environment configuration:
  - `VJA_EXTRACT_MODEL` defaults to `anthropic/claude-haiku-4-5`.
  - `VJA_MATCH_MODEL` defaults to `anthropic/claude-sonnet-4-6`.
  - `VJA_MATCH_EFFORT` remains `medium` by default.
- Preserve the current prompts, Pydantic schemas, max-token limits, Sonnet adaptive-thinking/effort
  behavior, system-prefix cache breakpoint, D-089 score clamp, per-posting failure isolation, and
  rerun idempotency.
- Normalize each paid response into: validated value; mutually exclusive uncached input/output/
  cache-read/cache-write tokens; LiteLLM catalog cost; actual upstream model; latency; request ID.
  Persist the actual upstream model on the existing posting/match row.
- Unsupported parameters, malformed responses, absent usage, missing catalog pricing, and a false
  zero cost fail loudly at the existing per-posting isolation boundary. `drop_params=False`; no
  router, fallback, or new retry policy.
- Keep the existing `pipeline_runs` schema. Stage summaries aggregate returned catalog cost and
  normalized tokens; no migration or per-call trace table is needed for this block.

### Explicitly out of Block 1

- No production model change, prompt/schema change, `no`-verdict optimization, candidate-provider
  credentials, auto-routing, fallback, proxy deployment, DB migration, discovery-agent migration,
  or generic LLM-read fetcher work.
- No claim that a named candidate exists at a particular identifier/price until Block 2 verifies
  it against current primary provider documentation/catalog data.
- No CI eval repair in this branch. The current Anthropic eval is run manually for parity; the
  documented-but-missing path-filtered CI job is repaired with the expanded harness in Block 2.

### Block 1 DoD

- Offline tests pin request construction, schema parsing, usage/cache normalization, actual-model
  persistence, catalog-cost aggregation, environment overrides, and loud failure paths.
- Existing matching/extraction integration tests still pin selection, isolation, and idempotency.
- The current real Anthropic extraction/matching eval passes manually through LiteLLM.
- Default suite, ruff format/check, mypy, import-linter, lock check, diff check, and production image
  build are green.
- D-090, INVARIANTS, CLAUDE, `.env.example`, testing/workflow/deploy docs, beta ledger, docs/17,
  and WORKLOG all describe the same live boundary and remaining blocks.

## Block 2 decision gate

Before either cutover, Hayden approves the fixture set, scoring rubric, minimum pass thresholds,
candidate list, run count, and maximum eval spend. The report must separate extraction from matching
and show at least: schema-pass rate, task-specific correctness, obvious-NO recall, rationale quality,
median/p95 latency, uncached/cache/output tokens, and catalog cost. A model that cannot support the
required structured-output/caching/reasoning parameters must be called out explicitly; the adapter
does not silently erase those requirements.

## Deployment rule

Block 1 requires no production secret or env mutation: the defaults route through the already-mounted
`ANTHROPIC_API_KEY`. A later provider cutover is incomplete until its credential is added to Secret
Manager and to the complete service/Job secret lists in `deploy/gcp/ship.sh`, and its exact model route
is set as a preserved non-secret Cloud Run environment variable. Rollback is an env/model-route change
to the last eval-passing model, with the existing image still provider-neutral.
