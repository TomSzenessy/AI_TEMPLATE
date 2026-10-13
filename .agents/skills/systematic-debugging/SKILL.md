---
name: systematic-debugging
description: Finds and proves the root cause of a failure before any fix; Use when a test, build, or flaky check fails, behavior is unexpected, a fix did not work, the user asks "why does this happen", or you are about to guess at a change.
---

# Systematic debugging

**Iron law: no fix without a confirmed root cause.** A symptom fix is a new bug.
The incident loop (observe, search the ledger, reproduce, diagnose, repair,
verify, reconcile) and the `EL-###` error ledger are owned by
[`docs/operations.md`](../../../docs/operations.md#failure-loop); this skill is
how to do its Diagnose and Repair steps well. Do not restate them.

Hurried, "obvious", or already-tried-something situations are exactly when this
applies. Systematic is faster than thrash.

## Phase 1: Investigate (no edits yet)

1. **Read the whole error**: full stack, exit code, file:line, warnings above
   it. The message usually names the cause.
2. **Search first**: `make where Q="<distinctive error text>"`. A known
   `EL-###` row means the fix is recorded; use it.
3. **Reproduce deterministically**: exact command, input, environment. Cannot
   reproduce: gather more data (logs, versions, timing); do not guess a fix.
4. **Check what changed**: `git diff`, `git log -p -- <path>`, new
   dependency, config, environment. A regression: `git bisect run <cmd>`.
5. **Multi-component flow** (CI to build to deploy, API to service to store):
   instrument every boundary once (what enters, what leaves, which env/config
   arrived), run, and read where the data first goes wrong. Then dig into
   that one component.
6. **Trace backward** when the error is deep in a call chain: symptom, the line
   that causes it, its caller, the value passed, who produced that value;
   repeat until you reach the original trigger. Fix there, never where it
   surfaced. No visible chain: log `new Error().stack` plus the inputs just
   before the failing call (to stderr; loggers may be silenced in tests). Test
   pollution (a stray file or state appears): run tests one at a time to find
   the polluter.

## Phase 2: Pattern

Find similar working code in this repo. Read the reference completely, not a
skim. List every difference between working and broken, however small. Name
the assumptions and dependencies (config, env, ordering) each side relies on.

## Phase 3: Hypothesis

1. Write one sentence: "The cause is X because Y" (Y is an observation).
2. Test it with the smallest change or probe; one variable at a time.
3. Wrong: discard it, form a new one from the new evidence. Do not stack
   fixes on a failed one.
4. Not understood: say "I do not understand X", research, or ask. Never
   pretend.

Separate in your notes: confirmed cause, contributing factors, hypotheses.

## Phase 4: Fix

1. **Failing test first.** The smallest automated reproduction (a script if
   there is no framework). Run it and watch it fail *for the right reason*
   (the bug, not a typo or setup error). A test that never failed proves
   nothing.
2. **One fix** at the root cause. No "while I am here" cleanups, no bundled
   refactor.
3. **Green**: the new test passes, the surrounding suite still passes.
4. **Prove the test guards the fix**: revert only the fix, the test must fail;
   restore, it must pass.
5. **Defense in depth** when bad data caused it: after fixing the source, add
   validation at the layers the data crosses (entry validation, domain
   invariant, environment guard that refuses the dangerous action, and a
   forensic log) so a different path cannot reintroduce it. Test that each
   layer catches the bypass.
6. Add the ledger row and close out per
   [operations](../../../docs/operations.md#error-ledger); verify the real
   artifact per [`docs/verification.md`](../../../docs/verification.md).

## Three failed fixes: stop

Counting every attempt. At three, do not try a fourth. Signs of a structural
problem: each fix exposes shared state or coupling elsewhere, a fix needs a
large refactor, each fix creates a new symptom. Question the design (is this
pattern sound, are we continuing from inertia?), write what you learned to the
issue, and decide the redesign with the owner before more patches. That is a
wrong architecture, not a bad hypothesis.

## Flaky tests: wait for conditions, not time

A fixed `sleep`/`setTimeout` guesses at timing and fails under load. Poll the
real condition with a short interval (about 10 ms), a hard timeout, and an error
that names what was awaited; re-read state inside the loop, never cache it.

```
wait_for(lambda: job.state == "done", what="job done", timeout=5)
```

A fixed delay is right only when testing real timing (debounce, throttle) or
after the trigger condition fired and the interval is known; comment why.
Also look for leaked shared state and order dependence (run the test alone).

## Evidence before claims

Never say fixed, passing, or done on "should", "probably", or an earlier run.
Run the command now, read the whole output and exit code, then state the claim
with that evidence. Linter green is not build green; a changed line is not a
fixed bug; a subagent's "success" is verified against the diff.

## Red flags and the truth

| Thought | Reality |
|---|---|
| "Quick fix now, investigate later" | The first patch sets the pattern. Investigate first. |
| "Just try changing X and see" | Guessing; it hides which change mattered. |
| "It is simple, no process needed" | Simple bugs have root causes; the process is quick for them. |
| "Emergency, no time" | Thrash costs more than diagnosis. |
| "I see the problem, fixing it" | Seeing a symptom is not understanding the cause. |
| "I will add the test after it works" | Untested fixes regress; test first. |
| "Several fixes at once saves time" | You cannot tell which worked and you add bugs. |
| "One more attempt" (after two) | Three failures mean question the design. |
| "No root cause, it is environmental" | Usually an unfinished investigation; if truly external, document what you ruled out and add a retry/timeout and logging. |
| "I will adapt the reference without reading it all" | Partial understanding guarantees bugs. |

Any of these: stop, return to Phase 1.

## Done

Cause confirmed with evidence, red-then-green test in the suite, one root-cause
change, `make done` fresh, real path observed, ledger and issue updated.

Upstream depth: `make upstream ID=superpowers-workflow` lists pinned files (e.g. deep stack → root-cause-tracing.md); fetch only the one your step needs.
