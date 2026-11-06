# Collaboration

<!-- index: operate | Sharing work: fetch, push, pull-first, CI after push, claims, issue comment types | several people or agents work on one repository -->
<!-- covers: tools/kit/gitsync.py tools/kit/cistatus.py tools/kit/prflow.py .gitattributes -->

Several people or agents on one repository (a team, a pair, or one person
running parallel agent sessions) lose work in three ways: one runs
on code the others do not have, two change the same files without knowing,
and a finding stays in one session's context. This page owns the rules and
the commands that prevent each. The session protocol in
[`AGENTS.md`](../AGENTS.md#session-protocol) is the short form.

## Shared code: fetch, push, pull first

| When | What the kit does | Command |
|---|---|---|
| Session start | The brief fetches the upstream (at most 10 s, never in CI), fast-forwards a clean tree that is only behind, and otherwise says how far behind or ahead the branch is. A resumed or compacted session fast-forwards only while it has committed nothing, and its stop-gate baseline moves with the pull. | `make start` |
| Stop | The stop gate names this session's uncommitted paths and its commits that are not pushed, once per turn; say why something stays local and stop. Commits the brief pulled are never counted as the session's. Without a remote, or inside CI, it says nothing. | hook |
| After a push | `make ci-status` reads the CI of the pushed commit: green, red, pending, inconclusive, none, unpushed, unavailable (every failed job ran zero steps, so billing/credits rather than code), or unknown (no `gh`, offline, inside CI). A red run on this session's pushed HEAD blocks `make done` and the stop gate; unavailable does not, and names the billing cause instead of pointing at logs that do not exist; an all-skipped success is unavailable too, because it verified nothing, and unreadable job details are `unknown`, never green. A green answer is cached for a day, anything else for five minutes. | `make ci-status` |
| Before a run others will rely on (a release build, a deploy, a benchmark, an official submission) | Refuses a dirty tree, unpushed commits, a diverged branch, or an unreadable upstream (exit 1); pulls new commits and exits 3 so the caller restarts on the new code; exit 0 means run as is. `CHECK_ONLY=1` never pulls (a frozen release); inside CI it exits 0. | `make pull-first` |

Commit verification excludes `issues` and `issue_comment` runs: GitHub attaches
those runs to the default-branch SHA even though they validate issue activity,
not that commit. Their independent validation results remain available in
GitHub Actions. Push and pull-request failures still count; other events
(including scheduled/manual runs) and runs with missing event metadata remain
in scope conservatively. If only issue-event runs exist, status is `none`
("no applicable commit verification"), never green. The query reads at most
100 runs; it is a bounded status snapshot, not proof that every workflow ran.
Cached answers carry this classification's scope version, so pre-isolation
answers are discarded and queried again; the existing expiry windows remain.

The session brief shows both HEAD and the configured default branch's CI
conclusion (the actual `origin/<default>` commit as of the start's last fetch).
One `gh run list` request reads at most 100 recent repository runs with a
2-second subprocess bound; a target omitted from that window reports `none`,
not green. Missing branch metadata/ref reports `unknown`, never a guessed
main/master status. Missing/offline `gh` also reports `unknown`.
The ignored diagnostic snapshot is reused for the same existing host hook
session ID from the current start invocation and unchanged HEAD/default target
pair; changed targets or a new session requery. A failed baseline write cannot
substitute an older persisted host ID. Without a real host ID (`make start` uses `local`), reuse is
limited to five minutes, not a claim of once-per-session behavior. This brief
can remain stale within a known session; it is not completion evidence.
Its separate cache never feeds targeted `make ci-status` or stop/done checks:
those retain their commit query, expiry and nongreen refresh rules.

Push each working step, at least every 30 minutes and always before stopping.
On a rebase conflict keep both sides' intent and rerun the tests; never
resolve by dropping the other side. Shared documents change on the default
branch; merge it into long-lived variant branches regularly.

## Batch finished work

One CI run per finished change set, on the exact tree that merges. The rules:

- **One branch per coherent change set.** Several small fixes that share an
  issue, an owner, or a review belong on one branch, not four.
- **Draft while iterating.** A draft PR is skipped by the heavy jobs (the leak scan still
  runs on every non-draft PR and every push), so a half-finished push does not
  pay for verification.
- **Local gate before ready.** Run `make done` yourself; `make ready` repeats
  it on the tree it will push and refuses a dirty tree or a failing gate.
- **One push when done.** `make ready` merges the default branch locally, runs
  `make done` once, pushes once, then `gh pr ready`. Do not re-run green CI to
  "be sure"; a re-run buys no assurance.
- **Batch several finished branches.** `make integrate BRANCHES="feature/a
  feature/b"` merges them into one integration branch, runs `make done` once,
  and opens one PR whose body carries every `Fixes`/`Closes`/`Resolves #N`;
  a conflict aborts the merge instead of guessing. Both commands re-check the tree
  after `make done`, because `repoctl sync` may rewrite a derived file.
- **Merge queue.** `ci.yml` and the specialist scans also run on
  `merge_group`, so the queue tests the combined tree once.
- **Tree-hash reuse.** A default-branch push whose tree is byte-identical to a
  head that already passed a `ci` run skips the heavy jobs; a tree that differs
  by any file runs them. The cheap gates and leak scan always run.
- **Leak-scan fixtures.** Prefer fixtures built at runtime. A `.gitleaksignore`
  fingerprint keyed to a commit is orphaned by a squash merge, so
  `make check` warns about one; use a path-scoped allowlist in
  `.gitleaks.toml` when a fixture must be tracked.
- **No required check is dropped.** Drafts, reuse, and batching change when a
  job runs, never whether a required check exists; never merge with a failed,
  pending, or skipped required check.

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

One API key, a rate limit, a staging database, or a quota is shared by
everyone who uses it. Before heavy or parallel use, say in the issue who uses
which resource when; during a run whose result matters (a load test, a
release, a paid batch), nobody else uses it.

## Append-only files

`.gitattributes` merges [`ERROR_LOG.md`](./ERROR_LOG.md) with `merge=union`, so
two branches that each appended an entry merge without a conflict. Add any other
append-only file the project keeps; never a file whose lines are edited in place.

## Agent transcripts

Transcripts, checkpoints, and session logs are private by default
([`security.md`](./security.md#agent-transcripts)).
