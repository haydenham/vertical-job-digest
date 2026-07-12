# Fetcher Interface Spec

*Build spec for Layer 1 (the ATS spine). Every ATS is a module behind one common interface, so an employer record
is "a pointer to a fetcher + an identifier." Adding an ATS = adding a module; adding an employer = adding a row.*

## The common contract

```python
@dataclass(frozen=True)
class RawPosting:
    external_id: str        # stable ATS id — THE diff key (D-016). Required.
    title: str              # best-available title from the source
    apply_url: str          # the link the digest will send users to
    location: str | None    # raw location string if present
    updated_at: str | None  # source's last-updated, if exposed
    raw: dict               # full untouched payload for this posting (stored as raw_payload)
    description: str | None = None  # best-available description text → feeds content_hash + Layer 2
                            # (Greenhouse `content` HTML; Lever `descriptionPlain`→`description`;
                            # Ashby `descriptionPlain`→`descriptionHtml`). May be plain or HTML.

class Fetcher(Protocol):
    ats_type: str
    def fetch(self, employer: Employer) -> list[RawPosting]:
        """Return all currently-open postings for this employer. Pure read.
        Raises FetchError on transport/parse failure (caught by the pipeline → loud alert, never silent)."""
```

Rules:
- **Deterministic, read-only, idempotent.** No DB writes inside a fetcher — it returns data; the diff job persists.
- **`external_id` must be the ATS's own stable id**, not something we synthesize from the title. All three JSON ATSs expose one.
- The fetcher does **not** extract structured fields (level, stack, comp). That's Layer 2. A fetcher only produces `RawPosting`.
- On any non-200 / unparseable response, raise `FetchError` — the pipeline records a `fetch_failure` and alerts. Silent decay is the enemy (Memo 02 §8).

## Per-ATS modules

Endpoints below are confirmed live against the seed set (2026-06-11).

### Greenhouse — `ats_type: greenhouse`
- **Endpoint:** `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`
- **Response:** `{ "jobs": [ { "id", "title", "absolute_url", "updated_at", "location": {"name"}, "content" } ] }`
- **Mapping:** `external_id = str(id)`, `title = title`, `apply_url = absolute_url`, `location = location.name`, `updated_at = updated_at`.
- `?content=true` returns the description inline (feeds `content_hash` + L2 without a second request).
- Verified seed examples: `amperon`, `camusenergy`, `janestreet`, `yesenergy`.

### Lever — `ats_type: lever`
- **Endpoint:** `GET https://api.lever.co/v0/postings/{slug}?mode=json`
- **Response:** JSON array: `[ { "id", "text", "hostedUrl", "applyUrl", "categories": {"location", "team", "commitment"}, "createdAt", "descriptionPlain" } ]`
- **Mapping:** `external_id = id`, `title = text`, `apply_url = applyUrl or hostedUrl`, `location = categories.location`.
- Verified seed examples: `arcadia`, `voltus`.

### Ashby — `ats_type: ashby`
- **Endpoint:** `GET https://api.ashbyhq.com/posting-api/job-board/{slug}` (add `?includeCompensation=true` for comp)
- **Response:** `{ "jobs": [ { "id", "title", "jobUrl", "applyUrl", "location", "employmentType", "publishedAt", "descriptionPlain" } ] }`
- **Mapping:** `external_id = id`, `title = title`, `apply_url = applyUrl or jobUrl`, `location = location`.
- Verified seed example: `weave-grid`.

### Workday — `ats_type: workday`  *(high-maintenance tier — later than weeks 1–2)*
- No single public pattern. Each tenant exposes an internal JSON API like
  `POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` with a JSON body `{limit, offset, searchText, appliedFacets}`.
- Requires **per-company config** (tenant, datacenter, site id) stored on the employer row / vertical config, and **loud failure alerts** — these endpoints shift.
- `external_id` = Workday's `bulletFields`/`externalPath` job id. Treat as best-effort; verify the apply link survives.
- Most seed `unverified` rows (the big utilities/banks/exchanges) will land here.

### Paylocity — `ats_type: paylocity`
- **Endpoint:** explicit per tenant: `GET https://recruiting.paylocity.com/recruiting/jobs/All/{uuid}/{name}`.
- **Response:** server-rendered HTML containing one complete `window.pageData = {"Jobs": [...]}` JSON object.
- **Completeness:** single authoritative response; a valid empty `Jobs` list is zero open, while transport,
  parse, or shape failures raise `FetchError`.
- **Mapping:** `external_id = str(JobId)`, `title = JobTitle`, `location = LocationName` (structured fallback),
  `updated_at = PublishedDate`, `apply_url = /Recruiting/jobs/Apply/{JobId}`.
- Descriptions are lazy-fetched from `/Recruiting/jobs/Details/{JobId}` for in-scope survivors.

### Phenom — `ats_type: phenom`
- **Endpoint config:** explicit tenant base plus query options, e.g.
  `https://careers.example.com?lang=en_us&country=us`; both values are required and enter request bodies.
- **List:** `POST {base}/widgets` with `ddoKey=refineSearch`, paginated by `from`/`size` against `totalHits`.
  A short result, changing total, malformed envelope, or page failure raises `FetchError`.
- **Mapping:** `external_id = jobId`, `title`, `apply_url = applyUrl`, `location`,
  `updated_at = postedDate`; list descriptions are absent.
- **Detail:** the same endpoint with `ddoKey=jobDetail` and `jobSeqNo=<jobId>` returns the full job object
  lazily for in-scope survivors. The public API accepts the stable `jobId` directly.

### BambooHR — `ats_type: bamboohr`
- **List endpoint:** `GET https://{slug}.bamboohr.com/careers/list`.
- **Response:** one authoritative `{ "meta": {"totalCount": N}, "result": [...] }` JSON object. The
  count must equal the result length; a valid count/result of zero is authoritative zero openings.
- **Mapping:** `external_id = str(id)`, `title = jobOpeningName.strip()`, `apply_url` = the public
  `https://{slug}.bamboohr.com/careers/{id}` page, `updated_at = None`.
- **Location:** prefer `atsLocation` city + state-or-province + country; fall back to `location`, then
  `Remote` when `isRemote` is true and no structured location exists.
- **Detail:** `GET https://{slug}.bamboohr.com/careers/{id}/detail` is lazy. Return only
  `result.jobOpening`; never expose sibling `formFields` application metadata. List descriptions stay absent.

### Pinpoint — `ats_type: pinpoint`
- **List endpoint:** canonical boards derive as `GET https://{slug}.pinpointhq.com/postings.json`;
  an explicit `endpoint` overrides the derived URL for provider-backed custom domains.
- **Response:** one authoritative `{ "data": [...] }` JSON object with no pagination count. A valid empty
  list is authoritative zero; malformed envelopes/entries, duplicate posting ids, transport failures, and
  non-JSON responses fail the whole fetch.
- **Mapping:** `external_id = str(id)` (the top-level posting id, not nested `job.id`), trimmed `title`,
  `apply_url = url`, `location = location.name`, and `updated_at = None` (the source exposes no posted or
  updated timestamp).
- **Rich list:** full description/responsibilities/qualifications/benefits/compensation are inline, so there
  is no lazy detail resolver. The untouched posting object is `raw`; its split semantic content fields are
  joined for `description` so any meaningful job-content change invalidates `content_hash`.

### Raw HTML — `ats_type: raw_html`  *(Layer 2 fallback, not Layer 1)*
- Universal fallback: fetch the rendered careers page text and LLM-read it. Belongs to Layer 2; listed here for completeness.
- For these, `external_id` is synthesized from a stable content signature (since there's no ATS id) — documented in the L2 spec when it's built.

### Unknown — `ats_type: unknown`
- Placeholder for seed rows not yet resolved. Skipped by the nightly fetch (not `active`-eligible until typed) so they never silently 404 in the loop.

## Endpoint construction (from employer row)

```
greenhouse → https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
lever      → https://api.lever.co/v0/postings/{slug}?mode=json
ashby      → https://api.ashbyhq.com/posting-api/job-board/{slug}
workday    → use the hand-set `endpoint` column (per-company)
paylocity  → use the hand-set `endpoint` column (per-company UUID/name path)
phenom     → use the hand-set tenant base + required `lang`/`country` query
bamboohr   → https://{slug}.bamboohr.com/careers/list
pinpoint   → https://{slug}.pinpointhq.com/postings.json (or explicit endpoint for a custom domain)
```
Pinpoint alone permits an explicit `endpoint` to override its derived template for a verified custom-domain
board. Other slug-derived providers keep deriving from the slug (some legacy seed endpoint values omit required
query options); Workday, Paylocity, and Phenom require explicit endpoint configuration.

## Politeness & health (policy, not etiquette — D & Memo 02 §8)
- Identifiable `User-Agent`, conservative rate limiting, one fetch per endpoint per day total (D-005).
- Respect `robots.txt` on the long-tail raw-HTML path.
- **Per-fetcher health check:** an employer that returned N>0 postings yesterday and 0 today is a likely breakage → alert, don't mass-close. The diff's close-detection must not be triggered by a fetch that simply failed.
- Every run updates `pipeline_runs` (`employers_fetched`, `fetch_failures`).
