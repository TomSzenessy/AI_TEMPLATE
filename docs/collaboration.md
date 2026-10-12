# Collaboration

<!-- index: operate | Sharing work: fetch, push, pull-first, CI after push, claims, issue comment types | several people or agents work on one repository -->
<!-- covers: tools/kit/gitsync.py tools/kit/cistatus.py .gitattributes -->

Several people or agents on one repository lose work in three ways: one runs
on code the others do not have, two change the same files without knowing,
and a finding stays in one session's context. This page owns the rules and
the commands that prevent each. The session protocol in
[`AGENTS.md`](../AGENTS.md#session-protocol) is the short form.

## Shared code: fetch, push, pull first

| When | What the kit does | Command |
|---|---|---|
| Session start | The brief fetches the upstream (at most 10 s, never in CI), fast-forwards a clean tree that is only behind, and otherwise says how far behind or ahead the branch is. A resumed or compacted session fast-forwards only while it has committed nothing, and its stop-gate baseline moves with the pull. | `make start` |
| Stop | The stop gate names this session's uncommitted paths and its commits that are not pushed, once per turn; say why something stays local and stop. Commits the brief pulled are never counted as the session's. Without a remote, or inside CI, it says nothing. | hook |
| After a push | `make ci-status` reads the CI of the pushed commit: green, red, pending, inconclusive, none, unpushed, or unknown (no `gh`, offline, inside CI). A red run on this session's pushed HEAD blocks `make done` and the stop gate; a green answer is cached for a day, anything else for five minutes. | `make ci-status` |
| Before a run that counts | Refuses a dirty tree, unpushed commits, a diverged branch, or an unreadable upstream (exit 1); pulls new commits and exits 3 so the caller restarts on the new code; exit 0 means run as is. `CHECK_ONLY=1` never pulls (a frozen final run); inside CI it exits 0. | `make pull-first` |

Push each working step, at least every 30 minutes and always before stopping.
On a rebase conflict keep both sides' intent and rerun the tests; never
resolve by dropping the other side. Shared documents change on the default
branch; merge it into long-lived variant branches regularly.

## Claims

Before starting, claim the issue: assign yourself, set `status:in-progress`,
and list the paths you expect to change in a comment. If they overlap an open
claim, say so to the user and to the other claimant before editing. Clear the
claim when the work merges or stops. A claim with no commit or comment for a
day may be taken over after a comment naming it.

## Issue comments as shared memory

Live work lives in issues ([ADR 0001](./adr/0001-issue-backed-write-ahead.md)), so
a goal issue's comments are the team's memory. Start each with one type:

| Prefix | For |
|---|---|
| `[change]` | what was pushed, by commit |
| `[run]` | an evaluation spent: commit, cases, result, link to the record |
| `[finding]` | something learned, with its confidence tag ([`experiments.md`](./experiments.md#6-learnings)) |
| `[decision]` | a choice, who made it, why, and what it rules out |
| `[blocker]` | what stops progress and who can unblock it |
| `[handoff]` | what the next person needs, or a link to the handoff |

Write for a teammate who was not there: numbers, commits, IDs, links, and what
follows from it.

## Shared resources

One API key, a rate limit, a session cap, or a quota is shared by everyone who
uses it. Before parallel runs, say in the goal issue who uses which resource
when; during a run that counts, one machine uses the key and nobody else does.

## Append-only files

`.gitattributes` merges [`ERROR_LOG.md`](./ERROR_LOG.md) with `merge=union`, so
two branches that each appended an entry merge without a conflict. Add any other
append-only file the project keeps; never a file whose lines are edited in place.

## Agent transcripts

Transcripts, checkpoints, and session logs are private by default
([`security.md`](./security.md#agent-transcripts)).
