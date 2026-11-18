# Collaboration

<!-- index: operate | Sharing work: fetch, push, pull-first, CI after push, claims, issue comment types | several people or agents work on one repository -->
<!-- covers: tools/kit/gitsync.py tools/kit/cistatus.py tools/kit/localci.py tools/kit/prflow.py .gitattributes -->

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
- **Local gate before ready.** Run `make done` and then `make ci-local`
  yourself; `make ready` repeats `make done` on the tree it will push and
  refuses a dirty tree or a failing gate.
- **One push when done.** `make ready` merges the default branch locally, runs
  `make done` once, pushes once, then `gh pr ready`. Do not re-run green CI to
  "be sure"; a re-run buys no assurance. The local run and the tree hash it
  recorded are the evidence the push relies on.
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

## Verify, then push once

`make done` runs a project-defined subset of CI. `make ci-local` runs the
workflow jobs themselves, from `project.toml [ci.local]`, on the committed
tree; [`local-ci.md`](./local-ci.md) owns the manifest, the groups, the states,
and the limits. The protocol:

1. **Start clean.** `make pull-first`; work on a branch or worktree.
2. **Iterate locally.** `make ci-local GROUP=<affected>` while editing; keep
   the PR draft and do not push to test.
3. **Finish on the real tree.** Merge the default branch locally, run
   `make done`, then the full `make ci-local`. Commit first: it refuses a dirty
   tree, and `DIRTY=1` records an unverified tree instead of evidence.
4. **One push.** Push that tree once and open or update one draft PR. Mark it
   ready only while the head tree equals the tree in
   `.agent/ci-local/last-run.json`; put that short hash and the summary in the
   PR body, together with every `[[ci.local.not_local]]` gate that remains.
5. **CI runs once.** `make ci-status` until green; it warns when the recorded
   local run is stale, dirty, or incomplete. If a workflow fails, reproduce the
   command locally, fix it, rerun the affected group and then the full run, and
   push once more.
6. **Combine, don't multiply.** Several finished branches become one
   integration branch (`make integrate BRANCHES="a b c"`), verified once, in one
   PR. Never open a second PR for a fix to an unmerged PR.
7. **Merge only a verified head.** CI green and the tree equals the locally
   verified tree. Never push an empty commit to retrigger.
8. **Release builds.** `make pull-first`, build locally with the release flags,
   full `make ci-local`, then one push or tag, recording commit and tree hash.

A local pass proves the mapped commands on this tree — not the runner image,
the OS/Python matrix, network isolation, GitHub-only permissions, or any
`not_local` gate. Those stay visible in the PR; a local pass is never a
substitute for CI's own checks. With `[ci.local] guard = true`, the pre-push
hook refuses a head without a passing recorded run (`CI_LOCAL_SKIP=1` bypasses
it deliberately).

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
