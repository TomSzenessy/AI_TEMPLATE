# Local CI

<!-- index: operate | Local execution of the workflow jobs: groups, skips, digests, the push protocol, and what a local pass does not prove | The next step is a push, Actions is metered or blocked, or a workflow job must be reproduced locally. -->
<!-- covers: tools/kit/localci.py tools/tests/test_localci.py .githooks/pre-push -->

GitHub Actions is metered, and an account-level spending limit or block can
remove the feedback loop entirely. That makes "push and see" an expensive way
to find out whether a workflow step passes, and a `make done` that never ran
`test-future`, ShellCheck, or a compose check is not evidence about those jobs.
`make ci-local` closes the gap: it runs the workflow jobs a laptop can
reproduce, on the committed tree, before the push. The remote half stays
`make ci-status`, which reads the one run that push spends.

The rule this page makes mechanical: **verify locally, then push once**
([`collaboration.md`](./collaboration.md#verify-then-push-once)).

## One command, three honest states

```bash
make ci-local                     # every mapped job, in every group
make ci-local GROUP=verify        # only the fast group while iterating
make ci-local GROUP="verify garden"
```

Every mapped job ends as one of:

| State | Meaning |
|---|---|
| `PASS` | every command in the manifest ran and exited 0 |
| `FAIL` | a command ran and exited non-zero; its log tail is printed |
| `SKIP` | a tool is missing/too old, or a `slow` job was not enabled — never a pass |

A `not_local` job is a fourth, separate state: it is a reviewed decision that
the job cannot run on a laptop, printed in every summary with its reason. It is
never executed and never counted as passed. Unlike `SKIP`, it does not force
`INCOMPLETE`, because the reason and the substitute evidence are already part
of the reviewed map; the PR lists them.

One log per job and a machine-readable record are written under `.agent/`
(ignored, never pushed):

```text
.agent/ci-local/<run>/verify-verify.log
.agent/ci-local/last-run.json     # commit, tree, per-job state, tools, exit
```

`last-run.json` is the evidence the PR cites. A run on a dirty tree is refused
by default; `DIRTY=1` records it as an **unverified tree**, which the guard and
`make ci-status` treat as no evidence.

## Exit codes

| Exit | Meaning |
|---|---|
| `0` | every selected mapped job passed (or skips were explicitly accepted) |
| `1` | at least one selected job failed |
| `2` | misuse: dirty tree, unknown group, or the manifest drifts from the workflows |
| `3` | incomplete: at least one selected job was skipped and `ALLOW_SKIP` was not set |

`ALLOW_SKIP=1` turns `3` into `0` for a run whose evidence is knowingly
incomplete, and the summary then says `PASSED WITH SKIPS`, never `PASSED`.
The `0/1/2/3` contract belongs to `repoctl ci-local`; GNU make itself exits `2`
for any failing recipe, so scripts and the pre-push guard call `repoctl`
directly when they must distinguish the states. GNU make also treats a trailing
`--flag` as its own option: the make spelling is the variable form
(`make ci-local CHECK=1`, `BLESS=1`, `PLAN=1`), while
`repoctl ci-local --check` keeps the flags.

## The map: `project.toml [ci.local]`

The workflows stay the source of truth for *what* CI does; the manifest says
*how* to do the same work here. Each mapped job names its workflow and job, the
tools it needs, and the commands:

```toml
[ci.local]
guard = false            # true: the pre-push hook enforces the recorded run

[ci.local.tools]         # minimums the doctor checks; missing tool = SKIP
python3 = "3.11"

[[ci.local.jobs]]
group = "verify"
workflow = ".github/workflows/ci.yml"
job = "verify"
tools = ["python3", "make"]
commands = [["make", "verify"]]
digest = "sha256:..."    # written by BLESS=1, reviewed with the workflow diff

[[ci.local.not_local]]
workflow = ".github/workflows/publish.yml"
job = "publish"
reason = "registry login and release tags; prove with a local image build and name the gate in the PR"
```

A command is an array of strings and is executed without a shell. Several
commands in one job run in order and stop at the first failure. A project adds
a group by naming it on a job; `GROUP` selects groups.

## Drift: the map cannot silently disagree with the workflows

`make check` fails when:

- a workflow job is neither mapped nor declared `not_local`;
- a declared job no longer exists (renamed or removed);
- a mapped job's `digest` does not match its reviewed workflow block.

After changing a workflow job, re-read that job's diff and run:

```bash
make ci-local BLESS=1   # refresh digests; review the project.toml diff and commit it
make ci-local CHECK=1   # validate only, no run
```

The digest covers the job's YAML block, read as text, so the kit needs no YAML
parser. Any consistent indentation under `jobs:` is read; a flow-style
`jobs: {...}` mapping is reported as unreadable instead of being silently
skipped. `BLESS` refuses to run while structural problems (an unmapped job, a
missing reason) remain: a fresh digest must not bless an incomplete map.

## Tools, skips, and the doctor

```bash
make ci-doctor          # tools needed, detected versions, declared minimums
```

A job whose declared tool is missing or older than its minimum is `SKIP`, and a
run with a skip is `INCOMPLETE` (`3`). That is deliberate: a missing toolchain
must not look like a pass. Install the tool, or accept the gap explicitly with
`ALLOW_SKIP=1` and say so in the PR.

Slow work (browser E2E, an OS matrix, an image build) is marked `slow = true`.
It runs only with `SLOW=1` (or `CI_LOCAL_SLOW=1`) and is otherwise listed as
`SKIP (slow; …)`. Jobs that genuinely cannot run here — deploy, publish,
provider APIs, code signing, OS-only runners — belong in
`[[ci.local.not_local]]` with the evidence the PR must carry.

## When to run which group

| Moment | Command |
|---|---|
| While editing, after a focused test | `make ci-local GROUP=<affected>` |
| Before the first push of a change set | `make ci-local` (or `SLOW=1` when the change touches a slow job) |
| After merging several finished branches | `make ci-local` on the integration branch, once |
| After changing a workflow | re-read the job, `make ci-local BLESS=1`, then the full run |
| Before a release build | `make pull-first`, build with release flags, full `make ci-local` |

A group is for the fast loop, not for the claim. Only a full run can be cited
as local verification of the tree.

## Verify, then push once

The same protocol is stated in [`collaboration.md`](./collaboration.md) and
applied by `make ready` / `make integrate`; this page owns the detail.

1. **Start clean.** `make pull-first`; work on a branch or a worktree, never
   the default branch.
2. **Iterate freely, commit locally.** Run focused tests and
   `make ci-local GROUP=<affected>` while editing. Keep the PR draft; do not
   push to test.
3. **Finish on the real tree.** Merge the current default branch locally, run
   `make done`, then `make ci-local` on the exact final tree. Commit everything
   first: the run refuses a dirty tree.
4. **One push.** Push once. Open or update one draft PR for the coherent change
   set; mark it ready only while `git rev-parse HEAD^{tree}` equals the tree in
   `.agent/ci-local/last-run.json`. Put that short tree hash and the local
   summary in the PR body.
5. **CI runs once.** `make ci-status` until green. If a workflow fails,
   reproduce that command locally, fix it, rerun the affected group and then
   the full run, and push once more. A red run is the author's, and the local
   map must grow to cover the step that failed.
6. **Combine, don't multiply.** Merge several finished branches into one local
   integration branch (`make integrate BRANCHES="a b c"`), verify once, and land
   one PR. Never open a second PR to fix an unmerged PR; amend the draft.
7. **Merge only a verified head.** Merge when the head's CI is green and its
   tree equals the locally verified tree. Never push an empty commit to
   retrigger, and never force-push a head CI already verified without rerunning
   local CI.
8. **Release builds.** `make pull-first`, build locally with the release flags
   (including the slow group), then one push or tag; record the commit and tree
   hash in the release note.

## Evidence the command records, and what it does not prove

`make ci-status` prints a warning when `.agent/ci-local/last-run.json` is for a
different commit or tree, is dirty, or is incomplete. That catches "verified
before the last amend".

A local pass proves the manifest's commands on this tree. It does **not** prove
the runner image, the OS/Python matrix, network isolation, GitHub-only
permissions, or any `[[ci.local.not_local]]` gate. The docs and the PR say which
gates stayed remote; a local pass is not a substitute for a GitHub-only check.

Nothing here reads a repository or provider key, calls the network, or runs a
`not_local` job: the runner executes only the commands the manifest declares.

## Optional pre-push guard

```toml
[ci.local]
guard = true
```

With `guard = true`, `.githooks/pre-push` (installed with the other hooks by
`make start`) refuses a push whose head has no recorded passing run: missing,
failed, incomplete, dirty, or recorded for another commit or tree. It reads
`last-run.json` and never runs the suite, so it stays fast. Bypass it
deliberately with `CI_LOCAL_SKIP=1` and say why in the PR; `git push
--no-verify` skips it entirely.

The guard is off by default: it makes the one-push rule mechanical, and it can
annoy a human doing a hotfix. A project that turns it on has to leave its last
local run on the exact tree `make ready` pushes — the merge `make ready` does
changes the tree, so run `make ci-local` after it and before the push, or leave
the guard off and let the remote run judge the merge.

## Limits

- This does not emulate GitHub-hosted runners and does not replace `act`; it
  replicates the commands and the working directory, not the machine.
- The map is reviewed by a human or agent, not derived from YAML. The digest
  makes stale reviews visible; it cannot decide whether the local command is a
  faithful substitute. Re-read the job when CI changes.
- Deployment, publishing, secrets, and provider state stay out of the local
  run by design.
