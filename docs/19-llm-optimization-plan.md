# LLM cost optimization — plan of record (D-090)

*Working execution plan accepted by Hayden on 2026-07-16. Read
`docs/INVARIANTS.md` → `WORKLOG.md` top → this file to continue after a reset. Every block is a
separate branch/review decision; Hayden commits and opens PRs.*

## Outcome and sequencing

Rolefeed must be able to evaluate and change extraction/matching models without provider SDK code
changes, then choose both models from measured quality, latency, and catalog cost. This work is a
beta/Robotics prerequisite, but it must not erase the production evidence from D-088/D-089.

1. **Block 0 — observe (CONTRACT FIX BUILT; post-deploy gate remains):** the July 17 audit passed
   D-086/D-089/D-090, confirmed NextEra's Radancy surge was expected DB catch-up, and exposed 14 Workday
   tenants reporting `total=0` after a nonzero first page. PR #92 merged July 20, so July 21—not the planned
   July 18 gate—was the first D-091 trace. D-092 accepts the proven zero-sentinel mode without weakening
   exact/unique guards and keeps two ambiguous 2,000-result boards failed closed. Observe one normal scheduled
   run after deploy; do not attribute fewer calls to model savings.
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

## Immediate handoff — deploy and observe D-092, then return to Block 2's decision gate

The July 21 scheduled execution `vja-nightly-djxjt` was the first run with D-091 instrumentation. It completed
once in 34m39s under the D-086 policy; its partial pipeline had 15/101 failures, all Workday. Each affected board
returned consistent later-page zeros, disjoint pages, an exact page-one row/unique-ID count, zero overlap, and
zero malformed IDs. Four other multi-page Workday boards repeated the original total and completed exactly.
Thirteen zero-sentinel boards ended on a short page. Airbus and Thales instead each reported exactly 2,000 and
returned 100 full pages—agreement with the reported target, but not proof that the source was uncapped.

**D-092 contract correction:** page one sets the target; later pages must consistently repeat it or consistently
report zero. Every unexpected/mixed total, incomplete/overlapping/malformed snapshot, and the ambiguous
first-page-only 2,000/full-page signature still raises before diffing. The D-091 shadow walk is retired in favor
of debug page evidence plus one compact summary. No manual board fetch, DB/schema/model/config change, or broad
cap workaround is included. After Hayden's branch review/commit/PR and deploy, one normal scheduled run confirms
the 13 restored boards and the two explicit cap failures.

Block 2 starts only after that observation and Hayden's approval of its fixtures, rubric, pass thresholds,
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
