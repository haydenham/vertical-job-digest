# Update documents

*What this directory is, and the rules for adding to it. Established 2026-08-02, when Rolefeed had
been live long enough that "what changed since launch" stopped being answerable from `WORKLOG.md`
alone.*

## What an update doc is

One file per **update** — a coherent group of fixes and features shipped to production together, in
the sense a user or a stranger reading the repo would recognize. `1.1.md` is the first.

It answers one question the other four documents deliberately do not: **what does this release
consist of, and what did it leave behind?** Everything else in the repo is organized by *when* it
happened or by *what is true now*. An update doc is organized by *what shipped as one thing*.

## Why the other docs do not cover it

| Document | Axis | Why it is not enough |
|---|---|---|
| `WORKLOG.md` | session, newest first | One session, one entry. A feature spanning three sessions has no single home, and the log is append-only narrative, not a summary. |
| `DECISIONS.md` | decision, append-only | Records *why* one call was made. Says nothing about what shipped alongside it, and most PRs carry no ADR at all. |
| `docs/INVARIANTS.md` | present tense | The current head. It deliberately erases history; a rule replaced last week reads as though it was always that way. |
| `docs/NN-*.md` plans | one block of work | A plan of record ends when its block lands. It does not know about the four unrelated fixes that shipped in the same fortnight. |

## Authority

**Memo tier — the lowest.** The authority order is unchanged and is not negotiable here: build specs
(`docs/04+`) > `CLAUDE.md` > memos, and this directory is a memo.

Concretely:

- A live cross-cutting rule goes in **`docs/INVARIANTS.md`**, never here.
- A re-litigable decision goes in **`DECISIONS.md`** as an ADR, never here.
- An update doc **points at** both, and adds only what neither is allowed to hold: the grouping, the
  measured before/after, and the ledger of what was consciously left undone.

If an update doc and INVARIANTS ever disagree, **INVARIANTS wins** and the update doc is a historical
record of a rule that has since moved. Do not edit a closed update doc to keep it current. That is
the whole point of closing it.

## Lifecycle

1. **Opens** when the first item after the previous update's boundary merges to `main`. In practice
   this means editing this file's index and creating `N.M.md` with a `Status: IN PROGRESS` line.
2. **Accumulates** as work lands. One row per merged PR; the prose comes at close, not per item.
3. **Closes** when the group is coherent enough to name. Set `Status: shipped <date>`, write the
   theme, and fill the carried-forward ledger.
4. **Never reopens.** A follow-up fix belongs to the next update, even if it repairs this one.

## Numbering

`MAJOR.MINOR`, and it is a **product** version, not a git tag or a package version — nothing in the
build reads it. `1.0` is the public launch (2026-07-28). Minors increment per update. A major would
mean the product changed shape, not that the number got large.

## What belongs in one

Required:

- **Boundary** — the exact commits/PRs the update covers, so there is no ambiguity about which
  release an item shipped in.
- **What shipped** — a table of items with PR number, ADR, date, and one line each.
- **Theme** — why these things went together. If no honest theme exists, say so rather than invent one.
- **Measured before/after** — this project measures before it fixes; the numbers belong in the record.
- **Known and not fixed** — the items named and deliberately deferred. This is the section that makes
  the file worth writing.
- **Open human items** — what is waiting on Hayden, not on code.

Not in one: implementation detail (read the ADR), API contracts (read the specs), or a rule anyone is
expected to act on (read INVARIANTS).

## Index

| Update | Status | Span | Theme |
|---|---|---|---|
| [1.2](1.2.md) | in progress | #120 → | The walk-through update: what happens to the people the funnel let in (plan: `docs/21`) |
| [1.1](1.1.md) | shipped 2026-08-02 · closed | #111 → #118 | The funnel update: let strangers see the product, and make what they see read well |
| 1.0 | shipped 2026-07-28 | through #110 (D-101) | Public launch. Recorded retroactively by `WORKLOG.md` 2026-07-28 and D-067/D-101; no update doc exists |
