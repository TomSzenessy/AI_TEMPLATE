---
name: review-practice
description: How to request, give, and receive code review in this repo (what to send the critic, review axes with severity, terse path-and-line findings, verifying feedback before implementing it); Use when work needs review before merge, you are asked to review a diff or PR, or you received review comments and must respond.
---

# Review practice

Three jobs: request a review, give one, receive one. Roles and verdicts are
owned elsewhere: the independent reviewer is the
[`critic`](../../agents/critic.md) role, briefs and returns follow
[`docs/delegation.md`](../../../docs/delegation.md), and the only verdict words
are the two defined in
[its verdict section](../../../docs/delegation.md#the-critics-verdict-and-its-evidence).
Do not invent others (no "approve", "LGTM", "needs work").

## Request a review

**When:** `make risk` says `high`; before merge; after a complex or
security-relevant fix; when the work is subjective or has no command oracle;
when stuck and a fresh view helps. Commit first, so the critic reads a real
`Commit:`.

**Send** (precise context, never your session history or your theory of why
it is right):

- `Issue` or the acceptance criteria verbatim.
- `Diff` as a range: `git merge-base origin/main HEAD` to `HEAD`.
- `Artifact` to open (rendered page, output file, API response).
- `Scope` of readable paths, and `Done when`.
- Missing pieces? `make review-packet ISSUE_FILE=<path>` builds the packet.

Do not review your own large diff inline: it burns the context you need to keep
driving, and you cannot falsify your own work. Delegate, read the return block,
act on `Blockers`, record per delegation.md. A reviewer never spawns reviewers
and never edits; it returns findings.

## Give a review

Read in this order:

1. **Intent**: what is this change for, what is the acceptance bar?
2. **Tests first**: do they pin behavior (not implementation), cover edge and
   error paths, and have names that state the behavior? Probe it: invert one
   condition the change adds, run the suite, restore the file. Tests that still
   pass do not guard that line.
3. **The code**, against five axes:
   - *Correctness*: matches spec, edge cases (null, empty, boundary), error
     paths, races, state consistency. Silence in the spec is not permission:
     judge by what a reasonable user would expect.
   - *Simplicity*: could this be fewer lines or fewer concepts? Abstractions
     earning their keep (not before a third use)? A new conditional bolted
     into an unrelated flow, repeated conditionals on one shape (missing
     model), dead code, compat shims, near-duplicate helpers? A refactor that
     leaves the concept count unchanged only relocates complexity.
   - *Architecture*: follows existing patterns (new ones justified), owner
     boundaries respected, no feature logic leaking into shared modules,
     dependencies one-way, explicit type boundaries instead of casts and
     silent fallbacks. Name the remedy, not just "this is complex": extract,
     collapse duplicate branches, delete a pass-through wrapper, move to the
     owner.
   - *Security and privacy*: untrusted input validated at boundaries, secrets
     out of code and logs, authz where needed, parameterized queries, output
     encoded, dependencies vetted ([`docs/security.md`](../../../docs/security.md)).
   - *Performance*: N+1, unbounded loops or fetches, sync work that should be
     async, hot-path allocation.
4. **Verification story**: which commands ran, was the real artifact observed,
   do docs bound by `<!-- covers: -->` match the change?
5. **Size**: around 100 changed lines reviews well, 300 only as one logical
   change, 1000 means split. A refactor mixed with a behavior change is two
   changes.

**Approval standard:** ship when it clearly improves code health and meets
acceptance, even if imperfect. Do not block on taste. Do not pass what you
have not run.

### Severity

| Tag | Meaning | Critic mapping |
|---|---|---|
| `bug` | Broken behavior, security hole, data loss, unmet criterion | `Blockers` |
| `risk` | Works but fragile: race, missing check, swallowed error, no test | `Blockers` if it can hurt users, else `Residuals` |
| `nit` | Style, naming, micro-optimisation; author may ignore | `Residuals` or drop |
| `q` | Genuine question, not a suggestion | answer before verdict |

Lead with highest leverage: correctness and security, then structure, then
cosmetics. Do not bury a real issue under nits.

### Finding format

One line each: `path:line — problem — fix`, with a severity tag when mixed.
Exact symbols in backticks; a concrete fix, not "consider refactoring"; no
hedging ("maybe", "I think": use `q`), no praise per line, no restating what
the line does.

```
src/auth.py:42 — bug — `user` can be None after `.find()`; guard before `.email`.
api/list.py:23 — risk — no retry on 429; wrap in `with_backoff(3)`.
util.py:88-140 — nit — 50-line fn does 4 things; extract validate/normalize/persist.
```

Drop terseness for security findings, design disagreements, and a new author who
needs the why: write a short paragraph with the evidence, then resume.

Also list anything you considered but set aside as out of scope, one line each
with the reason, so the owner can rule on it. Return in the critic block format.

## Receive a review

Applies to a critic return, a human comment, or an external bot.

1. **Read all of it** before reacting.
2. **Clear up the unclear first.** If any item is ambiguous, ask about it
   before implementing anything; items interact, partial understanding gives
   wrong work. "Understand 1, 2, 3, 6. Need clarification on 4 and 5."
3. **Verify each item against this repo**: reproduce the bug or read the code.
   Is it correct here? Does it break something? Why is it written this way
   (`git log -p`, `make where`)? Does the reviewer lack context? Does it
   conflict with a recorded decision in an issue or ADR? Cannot verify:
   say so and ask.
4. **Push back with evidence** (a test, a `path:line`, a command output)
   when it is wrong, breaks behavior, or is unused ("grep finds no callers;
   remove instead of extending?"). Architectural conflict: escalate to the
   owner, do not decide silently.
5. **Implement one item at a time**, ordered blockers (breakage, security),
   then simple fixes, then complex ones; run the focused check after each,
   then `make done`. Re-request the critic if a blocker changed code.
6. **Reply in the thread** (GitHub: reply to the comment, not top-level) with
   the fact: "Fixed in `path:line`: <what>". If your pushback was wrong:
   "Checked X; it does Y. Fixing." No apology essay.

No performative agreement: never "you are absolutely right", "great catch",
thanks, or "implementing now" before verifying. Actions and evidence are the
response.

| Excuse | Reality |
|---|---|
| "The reviewer is probably right, just do it" | Unverified changes add bugs; check first. |
| "Implement the clear ones, ask about the rest later" | Unclear items can change the clear ones. |
| "Its tests passed, so the feedback is moot" | Passing proves what ran, not what was missed. |
| "I will review my own diff, it is small" | Same blind spots as the author; use the critic at high risk. |
| "Add the proper version it suggests" | Check use first; unused code stays unbuilt. |

Upstream depth: `make upstream ID=addyosmani-agent-skills` lists pinned files (e.g. security → security-checklist.md); fetch only the one your step needs.
