---
name: handoff
description: Generate an end-of-session context handoff as a paste-ready system prompt for the next chat. Use at the end of a working session, or when the user says "handoff", "wrap up", "summarize for next chat", or wants to start a fresh thread without losing context. Exists to cut token usage — long threads grow context (and cost) super-linearly, so the user resets to a fresh chat seeded by this compact summary instead.
---

# Session Handoff

The user caps each thread at ~15 messages to avoid runaway token usage, then starts a fresh chat. Your job: compress THIS conversation into a compact block they paste as the **system prompt** for the next chat, so the new thread starts with full context and near-zero history cost.

## Output

Emit ONLY the block below — no preamble, no commentary before or after, nothing for them to trim. Write it addressed to the next assistant (so it reads as a system prompt), and open with a one-line orientation naming the project and the current branch/phase.

```
You are continuing work on <project> (branch <branch>, <phase/block>). Context from the prior session:

## Key decisions made
- <decision> — <one-line why / decision ID e.g. D-0xx if one exists>
- ...

## Code patterns established
- <file / convention / helper> — <what to follow so you match existing code>
- ...

## Next steps identified
- <next task> — <enough detail to resume cold: files to touch, the approach agreed>
- ...
```

## Rules

- **~200 words, hard cap 250.** Brevity is the entire point — this is a token-saving device, not a transcript. If forced to choose, keep decisions and next steps over background.
- **Only THIS conversation.** Don't restate generic project facts already in `CLAUDE.md`/`DECISIONS.md`/`WORKLOG.md` — the next session reads those itself. Capture what a fresh session would otherwise *miss*: judgment calls, things half-done, things explicitly rejected and why.
- **Be concrete.** Name files, functions, branch names, decision IDs, cost/number findings, and any pending verification (e.g. "live smoke not yet run").
- **Prefer the re-litigable.** Favor decisions someone might second-guess and patterns a cold start would violate.
- Don't run tools or edit files — just produce the block. End your turn after it.
