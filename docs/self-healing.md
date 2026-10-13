# Self-healing mechanics

<!-- index: operate | When a check may block, lifecycle hooks, failure output, ceremony by risk, and the gardener | A check fails, a gate blocks, or the kit itself changes. -->
<!-- covers: tools/kit/checks.py tools/kit/checkrun.py tools/kit/session.py tools/kit/gatechecks.py tools/kit/risk.py tools/kit/garden.py tools/kit/navigate.py .githooks/** .github/workflows/garden.yml -->

Agents follow written rules well at the start of a session and worst at the end,
after compaction, which is when cleanup and documentation get skipped. So the
maintenance rules here are **executed**, not remembered: lifecycle hooks,
checks in `make check`, and a scheduled gardener. Every mechanism is a
standard-library command in `tools/kit/`, so it works with any agent host.

This page owns the enforcement machinery: what makes a check block, the hooks
that run it, and the ceremony a change earns by risk. The rules the machinery
enforces live beside their code — doc-code bindings in
[`bindings.md`](./bindings.md), markers and file hygiene in
[`hygiene.md`](./hygiene.md), generated files in
[`generated-files.md`](./generated-files.md), capabilities and configuration in
[`capabilities.md`](./capabilities.md), template updates in
[`kit-update.md`](./kit-update.md), evals and trials in [`evals.md`](./evals.md),
issue rules in [`ISSUE_TEMPLATE.md`](./ISSUE_TEMPLATE.md), and error-ledger
rules in [`operations.md`](./operations.md).

## When a check may block

Every gate costs every future change some friction, so blocking is earned, not
assumed. A new or changed check **blocks** only when all three hold:

1. **Evidence:** skipping the step produced a worse product or codebase in a
   build trial, eval, or incident (not "an agent might forget").
2. **Cheap, named fix:** the message names the command or edit that clears
   it in minutes, not a review cycle.
3. **Deterministic and hard to game:** it checks the artifact itself (a file,
   a binding, a digest), not a ticked box or a keyword in prose.

Otherwise it is **advisory** (`make garden`, the brief) or an
**automatic fix** (`make sync`). Since #9 `markdown-links`, `command-references`,
`markers`, `budgets` are advisory, as is `readme-template-sections`. `file-hygiene` stays blocking; `[checks.file-hygiene] allow_paths` exempts one path with a reason ([`capabilities.md`](./capabilities.md#exempting-one-path-from-file-hygiene)) and advisory `file-hygiene-allowed` lists it too. Further rules:

- **One blocking point per concern.** Each later gate fires only on what the
  earlier one let through (`--no-verify`, uncommitted work), never on a
  decision already recorded, such as a `Docs-Unaffected` trailer.
- **Gate the outcome, not every step.** Require evidence once per feature or
  release (one UI review per feature and one before launch), not per commit
  or per screenshot.
- **Ceremony scales with risk.** `make risk` decides; a `low` change never
  inherits `high` ceremony.
- **No calendar rot.** A check must not start failing on an unchanged
  repository because time passed. Record and review ages (vision, stack
  decision, skill provenance, critic evidence) fail only `make readiness` from
  `private-preview` on; an issue's reviewer date never ages, because it
  belongs to the text it reviewed; during development `make garden` reports
  them and `make check` fails only on a future date.
  `make test-future` (also in CI, with `KIT_SLOW=1`) runs the suite 800 days ahead,
  so a date-pinned fixture fails now, not in two years.
- **One place decides blocking.** `Registry.blocks`, applied by `checkrun.run_checks`,
  is the only mechanism that turns a finding into a block: the check's `blocks=`
  declaration, then the project's downgrade ([`capabilities.md`](./capabilities.md#downgrading-a-check)).
  Each gate names the checks that fit its change set; the commit hook maps a non-empty result to exit 3, and
  `make verify` runs `doctor --checks-done` so no check runs twice. Date
  freshness is one helper, `core.date_out_of_policy`.
- **Retire what never fires usefully.** A check that only yields bypasses or
  ritual compliance is demoted or deleted in the next trial review.

## Lifecycle (any host)

| Moment | Host with hooks | Host without hooks | What happens |
|---|---|---|---|
| Session start or resume | `repoctl hook session-start` | `make start` | Brief: branch, recent commits, `HANDOVER.md`, map, the `make next` step, open findings, red CI, a template clone used as a project. Derived files are regenerated and the git commit gate is installed (adopted projects: [`adopt.md`](./adopt.md)). |
| Before context compaction | `repoctl hook pre-compact` | — | Writes `.agent/checkpoint.md` (uncommitted paths, docs still owed). |
| After a file edit | `repoctl hook after-edit` | — | Names the docs covering the edited path (once per session); regenerates derived files when a source changed; warns on edits to generated files. |
| Before declaring done | `repoctl hook stop` | `make done` | Gate over this branch's change set: owed docs, derived-file drift, dead bindings, red pushed CI (`ci-red`), an unreported kit change (`kit-upstream`), the stop hook also this session's unpushed work ([collaboration](./collaboration.md)), plus critic evidence for committed `high`-risk paths ([ceremony](#ceremony-by-risk)); `make done` also prints product completeness and advises on a stale UI review. It blocks again in a turn only on changed findings (five at most); it holds a session on new `make check` findings, and one that changed product-surface code while must features are open or `features.csv` is invalid ([`building.md`](./building.md)); `make done` also runs every test and predicts the commit gate. |
| Every commit | `.githooks/commit-msg` (any agent or human) | same | Refuses a commit whose staged covered code skips its doc (unless the message carries a `Docs-Unaffected:` trailer), and derived-file drift when the commit touches a source. In a merge commit, paths the merged branch brought in skip the owed-doc check (already judged); the rest is checked. Exit 3 means blocked; a broken plugin or kit also blocks (see [A broken check](#a-broken-check-is-a-finding-not-a-traceback)). Bypass with `--no-verify`. |

Owed docs (`doc-coupling`), critic evidence and `surface-docs` are registry
checks, so `[checks]` downgrades apply; `surface-docs` counts a surface's
`extra_paths` as owned.

The commit gate is installed (`core.hooksPath=.githooks`) only when the
repository has no hooks path and no active hooks in `.git/hooks`; otherwise the
brief says so and you call `.githooks/commit-msg "$1"` from your existing hook
or hook manager, so nothing already in use is switched off.

Claude Code receives the hooks through the generated `.claude/settings.json`.
Other hosts read [`AGENTS.md`](../AGENTS.md), which tells them to run the make
targets, and every host meets the git commit gate. `make handover` writes the
ignored `HANDOVER.md` from [`handoffs/TEMPLATE.md`](./handoffs/TEMPLATE.md)
with the time, branch, commit, uncommitted paths, and owed docs filled in.

## A broken check is a finding, not a traceback

Every finding in `make check` and `make garden` is prefixed `[check-name]`, and
a failing blocking check's `reason` is printed once under it. A check that raises
becomes `[name] check name crashed: <Type>: <message>` (blocking when the check
blocks) while the others still run; a malformed doc, invalid UTF-8 file, eval,
trial, or manifest value yields one named line, and `REPOCTL_DEBUG=1` restores
the traceback for an internal error. A closed pipe (`repoctl map | head`) exits
quietly with status 0.

A project plugin (`.agents/commands/*.py`, `.agents/checks/*.py`) that fails to
import is isolated: the kit's commands and every other plugin still run, `make
check` reports a blocking `[plugin-load] <file>: <error>`, and the commit gate
blocks until the file is fixed or deleted. `hook ...` is dispatched before the
argparse tree is built, the session brief lists the plugin files, and the hook
skips only (with a loud warning) when no launcher or Python 3.11+ exists.

## Ceremony by risk

`make risk` classifies this branch's changed paths with `project.toml [risk]`
globs: `low` needs `make check` only, `normal` follows the full build and repair
loop (with a critic for subjective or commandless work), and `high` (CI, tooling, agent instructions, security, auth, and migrations by default) adds an
independent critic. Tune the globs per project. Never widen `low` to dodge a gate.

### Critic evidence the gate can read

For committed `high` paths, completion gates read `.agent/critic.md`
([contract](./delegation.md#the-critics-verdict-and-its-evidence)):

- **`Verdict:`** must belong to the contract's vocabulary. `blocker` and
  unknown verdicts (including legacy `ship`) fail, never pass softly.
- **`Commit:`** names HEAD, or an ancestor whose subsequent committed paths
  are **all `low`** under current risk rules. Commit high-risk work before
  review; any later `normal` or `high` change requires a fresh review.
  History includes every commit and merge parent, reverted changes,
  deletions and both rename paths — not just the final net diff.
- Missing records/fields, non-ancestor commits, and unreadable HEAD/history
  fail with a named fix.

Only committed paths are judged; a dirty tree is not yet a reviewed diff.
`[governance].profile = "minimal"` skips this gate, handing review to the host.

## Write-ahead issues

The write-ahead record — when one is required before a change, its shape, the
`Local-WAL` draft route, and the `[governance].profile` levels — is defined in
[`ISSUE_TEMPLATE.md`](./ISSUE_TEMPLATE.md). An active vulnerability or
sensitive personal data takes the private route in
[`../SECURITY.md`](../SECURITY.md) instead of a public issue.

## The gardener

`make garden` aggregates every finding above plus advisory items (upcoming
deprecations, paragraphs repeated across documents, unbound docs, skill
reviews older than `[kit].skill_review_days`, GitHub metadata drift, npm pins behind their latest release) and runs each
surface's own `garden` commands, for example a dead-code finder:

```toml
[[surfaces]]
id = "web"
garden = [["npx", "knip"]]
```

The weekly report-only workflow (`.github/workflows/garden.yml`) publishes a job summary. A `doc-gardener` or `implementer` subagent fixes
findings, one root cause per change (see [`delegation.md`](./delegation.md)).

## Scale and limits

- `make where` searches with `git grep` (falls back to a Python scan outside
  git) and skips files over 400 KB; it also scores indexed doc
  descriptions/triggers and read-only `resources.toml` entries (id, summary,
  source). Doc bindings are cached by size and mtime in ignored `.agent/cache/`,
  so the per-edit hook does not re-read every doc.
- Staleness inspects the newest 2000 non-merge commits; a document last
  committed before that window is not judged.
- The stop gate judges only what this session changed: `session-start` records the dirty paths with
  content hashes and the commit inside `.git`; `stop` judges paths whose content differs plus paths
  committed since (no snapshot, or a start commit no longer an ancestor: the whole tree), with the
  commits' `Docs-Unaffected` trailers ([`bindings.md`](./bindings.md)) as `make done` does. A
  finding is raised once per turn until fixed or exempted; `make done` judges the whole branch.
  Resume refreshes only regenerated writes/removals after a proven clean automatic fast-forward
  with no session commits. Errors are not paths; own/dirty work and other healing stay owned.
  Input/output catalog: [`generated-files.md`](./generated-files.md).
- Hooks, the git gate, and `make` run through `tools/repoctl`, which picks the
  newest Python 3.11+ on `PATH` even when `python3` is an older system
  interpreter (override with `REPOCTL_PYTHON` or `make PYTHON=...`). Windows
  hosts run it from Git Bash or WSL.
