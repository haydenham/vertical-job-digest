# Session bootstrap template

Paste the block below into a fresh session (e.g. after `/clear`) and fill the two
`<...>` slots. It points the new session at the canonical docs rather than pasting
context into the prompt — `WORKLOG.md`'s top entry is the handoff, so there is no
200-word summary to copy. (If a session ends without a good WORKLOG entry, fix that
before clearing; that entry is what the next session relies on.)

---

```
Session handoff — vertical-job-agent-starter

Read before doing anything (read them yourself, don't ask me to summarize):
1. docs/INVARIANTS.md   — current cross-cutting rules (read first)
2. WORKLOG.md           — top entry = where we are
3. DECISIONS.md         — only the ADRs the task touches
(CLAUDE.md auto-loads. Don't re-read whole files you won't change.)

Task this session: <one-line goal>

Process: plan mode first, run every decision through me, branch-only (I commit/PR),
DoD = green gates + updated docs.

Give me a 3-line readback of where we are + your understanding of the task
before proposing a plan. If WORKLOG's top entry looks stale or mid-thought, say so.
```

---

**Why it's shaped this way**
- Point, don't paste: the canonical docs carry the depth; the prompt just aims the session at them. This is what the INVARIANTS/WORKLOG system is *for*.
- The readback line is cheap insurance against scope-drift — it forces the session to prove it loaded context before proposing, and flips the "is the handoff complete?" judgment onto the side that can actually see the docs.
- "Don't re-read whole files you won't change" keeps it from burning context on a codebase sweep; it can use the `Explore` subagent for "where does X live" questions instead.
