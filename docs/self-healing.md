# Self-healing mechanics

<!-- index: operate | When a check may block, hooks, doc-code bindings, deprecation expiry, budgets, generated files, gardener, evals | A check fails, docs drift, a host is added, or the kit itself changes. -->
<!-- covers: tools/kit/checks.py tools/kit/docsync.py tools/kit/hygiene.py tools/kit/adapters.py tools/kit/session.py tools/kit/garden.py tools/kit/navigate.py tools/kit/risk.py tools/kit/capabilities.py tools/kit/evals.py tools/kit/trial.py tools/kit/kitupdate.py .agents/trials/** tools/kit/gitinfo.py tools/kit/derive.py tools/kit/scaffold.py tools/kit/config.py tools/kit/reachability.py tools/kit/coupling.py tools/kit/signatures.py .githooks/** .github/workflows/garden.yml .agents/evals/** -->

Agents follow written rules well at the start of a session and worst at the end,
after compaction, which is when cleanup and documentation get skipped. So the
maintenance rules here are **executed**, not remembered: lifecycle hooks,
checks in `make check`, and a scheduled gardener. Every mechanism is a
standard-library command in `tools/kit/`, so it works with any agent host.

## When a check may block

Every gate costs every future change some friction, so blocking is earned, not
assumed. A new or changed check **blocks** only when all three hold:

1. **Evidence:** skipping the step produced a worse product or codebase in a
   build trial, eval, or incident (not "an agent might forget").
2. **Cheap, named fix:** the message names the command or edit that clears
   it, and that fix costs minutes, not a review cycle.
3. **Deterministic and hard to game:** it checks the artifact itself (a file,
   a binding, a digest), not a ticked box or a keyword in prose.

Otherwise it is **advisory** (`make garden`, the session brief) or an
**automatic fix** (`make sync`). Further rules:

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
  belongs to the text it reviewed; during development `make garden` reports them and
  `make check` fails only on a future date.
  `make test-future` (also in CI) runs the whole suite 800 days ahead, so a
  fixture or check pinned to a date fails now instead of in two years.
- **Retire what never fires usefully.** A check that only ever produces
  bypasses, trailers, or ritual compliance is demoted to advisory or deleted
  in the next trial review.

## Lifecycle (any host)

| Moment | Host with hooks | Host without hooks | What happens |
|---|---|---|---|
| Session start or resume | `repoctl hook session-start` | `make start` | Brief: branch, recent commits, `HANDOVER.md`, map, the `make next` step, open self-healing findings. Derived files are regenerated and the git commit gate is installed. |
| Before context compaction | `repoctl hook pre-compact` | — | Writes `.agent/checkpoint.md` (uncommitted paths, docs still owed). |
| After a file edit | `repoctl hook after-edit` | — | Names the docs covering the edited path (once per session); regenerates derived files when a source changed; warns on edits to generated files. |
| Before declaring done | `repoctl hook stop` | `make done` | Gate over this branch's change set: owed docs, derived-file drift, dead bindings, expired, undated, or unfinished markers, plus critic evidence when committed `high`-risk paths changed (see [Ceremony by risk](#ceremony-by-risk)); `make done` also prints product completeness and, as advice, a stale UI review ([`building.md`](./building.md)). The hook blocks once; `make done` also runs every test and predicts the commit gate for uncommitted work, so the two never disagree. |
| Every commit | `.githooks/commit-msg` (any agent or human) | same | Refuses a commit whose staged covered code skips its doc (unless the message carries a `Docs-Unaffected:` trailer), plus marker checks, and derived-file drift when the commit touches a source. In a merge commit, paths the merged branch brought in skip the owed-doc check (its commits already passed it or recorded a trailer); anything else staged is checked as usual. Exit 3 means blocked; a crashed kit never blocks a commit. Bypass deliberately with `--no-verify`. |

The commit gate is installed (`core.hooksPath=.githooks`) only when the
repository has no hooks path and no active hooks in `.git/hooks`; otherwise
the brief says so and you call `.githooks/commit-msg "$1"` from your existing
commit-msg hook or hook manager, so nothing already in use is switched off.

Claude Code receives the hooks through the generated `.claude/settings.json`.
Other hosts read [`AGENTS.md`](../AGENTS.md), which tells them to run the make
targets, and every host meets the git commit gate. `make handover` writes the
ignored `HANDOVER.md` from [`handoffs/TEMPLATE.md`](./handoffs/TEMPLATE.md)
with the time, branch, commit, uncommitted paths, and owed docs filled in.

## Documentation that tracks the code

A document declares what it describes with one comment near its top, such as
`<!-- covers: src/billing/** docs/api/billing.yaml -->` (repository globs:
`*`, `?`, `**`). From that single declaration:

- `make where Q="<path or term>"` and the after-edit hook name the owning doc.
- **Dead binding** (a glob matches no file): the code moved or died, so
  `make check` fails until the binding follows it.
- **Stale document**: a commit newer than the document's last commit touched
  covered paths. `make check` fails. If a change truly does not affect the doc,
  record that in the commit with a trailer, `Docs-Unaffected: docs/x.md <reason>`
  (a reason with no path exempts all documents; a value that starts with a
  non-document path or glob, such as `tools/** untouched`, exempts nothing). Git's own trailer parsing is
  used everywhere: trailers belong in the message's last paragraph, and a
  trailer without a reason exempts nothing.
- **Owed document**: covered paths changed on this branch while the doc did not;
  the stop gate and `make done` report it before history even exists.
- **Command references**: every backticked `make <target>` or `repoctl <command>`
  in Markdown, and every `make` line in a code fence, must exist. A `make`
  reference resolves to the nearest Makefile above the document (and the
  files it includes, such as `kit.mk` after `make adopt`), so subprojects and
  trial seeds keep their own targets.

Bind documents that explain behavior (architecture, module cards, runbooks, API
notes). Pure policy documents need no binding. Staleness needs full history:
CI checks out with `fetch-depth: 0`, and shallow clones skip it.

## Code that cannot rot silently

Markers are plain comments and work in any language:

- `DEPRECATED(remove-by=YYYY-MM-DD, use=<replacement>)` next to replaced code.
  `make check` fails after the date, so a duplicate path either dies or gets a
  deliberate new deadline. `make garden` lists dates due within 30 days.
- A language deprecation annotation (`@deprecated`, `@Deprecated`) needs a
  `remove-by=` date on its line or within the next three lines.
- Task markers in code must reference an issue (`#123`, a URL, or `Local-WAL`),
  because open work lives in the issue register, not in comments.
- `FILL-IN:` placeholders left by `make new` fail until replaced, so a
  half-written skill, role, or doc cannot rot unnoticed.
- A workflow `run:` block longer than 10 lines fails: CI logic belongs in
  `tools/` where it is unit-tested and runs locally (`repoctl ci <check>`).

## Files that justify themselves

A compact repository is the one property that every reader pays for, so it is
checked rather than hoped for.

- `orphan-files` **blocks** on a tracked file that nothing reaches: no document's
  `covers:` glob claims it, `make sync` does not generate it, no code imports or
  names it, and it is not in `[repository].infrastructure_paths`. The fix is one
  edit — import it, bind it, or delete it.
- Kit artifacts are exempt by default, from a list built out of the kit's own
  constants (`tools/kit/reachability.py`), so a project never has to justify a
  file the kit itself wrote.
- `host-read-config` **advises** on files only a host convention reads (editor,
  git, hosting, scanner config). Advice, not a block: the kit cannot model every
  host's conventions, and a wrong block is permanent in a project that has no
  upgrade path.

## Structure you can see

- `change-coupling` **advises**, from recent git history, when two areas keep
  changing together. That is what a wrong seam looks like over time, and it is a
  judgement, so it never blocks.

## Known failures, recognised

Every entry in `docs/ERROR_LOG.md` carries a key (`EL-001`…). When a blocking
check produces a finding matching a recorded signature, `make check` prints the
key and its permanent fix. A known failure is recognised in one step instead of
re-derived — the difference between debugging and pattern-matching. Fresh
failures add no line, so the ledger cannot manufacture a match.

## Product guardrails

Steps a fresh agent skipped in a real build trial are checks, each naming its fix:

- A tracked backlog (`docs/*WAL*.md`, `TODO.md`, `BACKLOG.md`, `TASKS.md`,
  `ROADMAP.md`) fails: live work goes to issues, or to ignored `.agent/wal/`
  (`make issue` writes it there when the repository has no GitHub remote).
- Every active product surface needs an owning doc: some `<!-- covers: -->`
  binding must match files under its path.
- In a UI project (`[kit].ui_kinds`, by `project.toml` kind) an accepted vision
  requires `docs/design.md`. (A rule that `quality_oracle` must mention
  `ux-quality` was retired: a keyword in prose is not a review; the real
  `make ui-review` gate in [`building.md`](./building.md) replaced it.)
- Owners in `project.toml` must be handles or team names, not emails.

## Context budgets

`project.toml [budgets]` maps globs to byte limits for files agents load often
(about 4 bytes per token). An over-budget file fails `make check`; move detail
into a linked owner document instead of growing the router.

## Derived files: one source each

Nothing that can be generated is maintained by hand. `make sync` (also run by
`make done`, the session-start hook, and the after-edit hook) renders:

| Derived | Single source |
|---|---|
| `.claude/skills/*`, `.claude/agents/*` (redirect stubs) | `.agents/skills/*/SKILL.md`, `.agents/agents/*.md` frontmatter |
| `.claude/settings.json` (hooks, pre-approved kit commands) | the kit, plus optional `project.toml [adapters.claude]` |
| `.mcp.json` | `.agents/mcp/*.toml` routes of enabled packs (servers are still approved per person) |
| The command block in the `Makefile` (`kit.mk` after `make adopt`) and `make help` | each `@command` declaration in `tools/kit/commands.py` and `.agents/commands/` |
| The project rules block in `AGENTS.md` | `.agents/rules/*.md` without a `scope` |
| The tables in [`README.md`](./README.md) | each document's `<!-- index: group \| owns \| read when -->` line |
| The role table in [`delegation.md`](./delegation.md) | role frontmatter (`description`, `access`, `tier`) |
| The description block in the root `README.md` | `project.toml [repository].description` |
| GitHub description, topics, template flag (`make github-sync`) | `project.toml [repository]`; `make garden` reports drift |

Generated host stubs cover only capabilities of enabled packs.
`make check` fails on any drift and on hand-written files in a generated host
directory. Add a host by adding a renderer in `tools/kit/adapters.py` and
listing it in `project.toml [adapters].hosts`. Codex, Copilot, and Cursor read
`AGENTS.md` and `.agents/skills/` directly.

## Extending: one model for every capability

Skills, agent roles, docs, rules, checks, commands, MCP routes, and packs are
all capabilities: one file each, declaring `name`, `description`
(`<what>; <when>`), and an optional `pack`, read by one loader
(`tools/kit/registry.py`; the decision is
[ADR 0002](./adr/0002-one-capability-model.md)). Adding the file adds the
capability; nothing is registered by hand.

`make similar Q="<need>"` answers first, across every kind and pack: reuse
(score at or above `[kit].overlap_limit`), read the closest match first (at or
above half of it), or create.
`make new KIND=skill|agent|doc|rule|check|command|mcp|pack NAME=<kebab> DESC="<what>; <when>" [PACK=<pack>]`
is the one way to add one. It refuses a near-duplicate of the same kind
(`FORCE=1` overrides), writes valid metadata, registers a first-party skill in
`[capabilities].local_skills`, regenerates every derived file, and leaves
`FILL-IN:` lines for the content. Refining a capability is an ordinary edit of
its file; the after-edit hook regenerates what depends on it.
Agent-instruction paths are `high` risk, so changes to them get a critic.

| Kind | File | What the kit does with it |
|---|---|---|
| rule | `.agents/rules/<name>.md` (`scope:` globs optional) | no scope: one line in `AGENTS.md`; scoped: the after-edit hook delivers it once per session when a matching path is edited, and `make where <path>` lists it |
| check | `.agents/checks/<name>.py` with `@check(name, description, blocks=..., reason=...)` | runs in `make check` and the gates when it blocks, in `make garden` otherwise; a blocking check without a reason fails to load (the blocking rule above) |
| command | `.agents/commands/<name>.py` with `@command(name, description, args=(arg("--x", var="X"),))` | becomes `repoctl <name>` and, after `make sync`, `make <name> X=...`; make variables reach it as quoted data |
| mcp | `.agents/mcp/<name>.toml` | rendered into host config when enabled (see [`resources.md`](./resources.md)) |
| pack | `.agents/packs/<name>.md` (`default: on` or `off`) | groups capabilities; `project.toml [packs]` overrides the default |

A check is a function of a context (`root`, `project`, `files`, `bindings`)
that returns findings, each naming its fix. Kit checks live in
`tools/kit/checks.py` and kit commands in `tools/kit/commands.py`; a project's
own go in `.agents/`, so `make kit-update` never conflicts with them.

**Packs** keep rarely needed capabilities out of every session. A pack that is
off contributes no host stubs, no `AGENTS.md` rule lines, no running checks,
and no `make help` lines, and its commands refuse with the line that switches
it on; it still appears in `make capabilities`, `make where`, and
`make similar`. The kit ships `product` (on: the product driver in
[`building.md`](./building.md)) and `measure` (off: `make eval`, `make trial`;
the template switches it on). A third-party skill, whose files are pinned by
digest, records its pack in its `[[skills]]` provenance entry.

## Configuration

Policy a project may change lives in `project.toml`, with built-in defaults
when a key is absent: `[packs]` (switch packs on or off), `[kit]` (docs index groups, unbound-doc exemptions,
overlap limit, deprecation warning window, skill review age, UI project kinds,
eval model, Playwright version and previewable kinds for `make ui-review`), `[adapters.claude]`
(tier-to-model and access-to-tools maps, pre-approved commands), `[risk]`
(tier globs and optional ceremony text), and `[budgets]` (byte limits for any
glob, including product code).

Entry files must *load* the router, not just point at it. `CLAUDE.md` imports
it with `@AGENTS.md`. A pointer-only version failed the fresh-agent benchmark
(4/5): a one-turn answer skipped the read and invented a commit trailer. With
the import, Claude scored 5/5, at about 35% more cost per cold single-shot
task, which the `AGENTS.md` budget keeps bounded.

## Ceremony by risk

`make risk` classifies this branch's changed paths with `project.toml [risk]`
globs: `low` needs `make check` only, `normal` follows the full build and repair
loop (with a critic for subjective or commandless work), and `high` (CI, tooling, agent instructions, security, auth, and migrations by default) adds an
independent critic. Tune the globs per project. Never widen `low` to dodge a gate.

### Critic evidence the gate can read

A critic is cheap to request and easy to skip, so the completion gate reads proof
that one ran (`tools/kit/session.py`): when this branch has **committed** `high`
paths, `make done` and the stop hook look for `.agent/critic.md` (ignored, so the
evidence never rides along in a commit).

The record is the [`critic`](../.agents/agents/critic.md) role's return saved
verbatim, and it is checked field by field:

- **`Verdict:`** must be exactly `blocker` or `ship-with-residuals`. `blocker`
  fails the gate (fix what it lists, then ask again), and any other word — prose,
  "looks good", `accept` — fails as an unknown verdict rather than a softer pass.
- **`Commit:`** must be the current HEAD, so evidence about older work cannot
  vouch for today's change set. That fixes the order: commit the change, then run
  the critic on that commit, then save its return — a record written before the
  commit goes stale the moment the commit lands.
- Missing record, missing `Verdict:`, or a record bound to another commit each
  fail with a message naming the fix, so the gate teaches the protocol instead of
  only reporting it.

Two deliberate exemptions keep the gate from being friction: it reads committed
paths only (a critic reviews a diff; a dirty tree is not one yet), and
`[governance].profile = "minimal"` skips it, because that profile hands issues and
review to the host.

## Write-ahead issues

Before a behavior, schema, contract, security, privacy, or operational change,
the router in [`AGENTS.md`](../AGENTS.md) requires a search of the issue register
and `docs/ERROR_LOG.md` first, then one issue per independent root cause carrying
intended behavior, scope, risks, and evidence-producing acceptance criteria
**before** implementation. The mechanics behind that rule:

- `make issue TITLE=... BODY=<file> TYPE=... PRIORITY=... AREA=... TOPIC=...`
  validates against the open and closed register and files on GitHub; the body
  format is [`ISSUE_TEMPLATE.md`](./ISSUE_TEMPLATE.md).
- With no GitHub remote, `make issue WAL=Local-WAL-001 …` (or `WAL=all`) writes
  the draft to ignored `.agent/wal/` instead, which counts as the write-ahead
  record.
- Active vulnerabilities and sensitive personal data never go in a public issue:
  use the private route in [`SECURITY.md`](../SECURITY.md). The disclosure class
  is an owner decision, and uncertain content stays private.
- Live work lives in the issue register, never in a Markdown backlog; the tracked
  backlog check above fails `docs/*WAL*.md`, `TODO.md`, `BACKLOG.md`, `TASKS.md`,
  and `ROADMAP.md`.
- `[governance].profile` sets how much friction the gates apply: `agent-first`
  (default, compact contract), `regulated` (full contract and launch gates),
  `minimal` (the host owns issues). Change it deliberately and record the reason
  in the issue.

## The gardener

`make garden` aggregates every finding above plus advisory items (upcoming
deprecations, paragraphs repeated across documents, unbound docs, skill
reviews older than a year, GitHub metadata drift, npm pins behind their latest release) and runs each
surface's own `garden` commands, for example a dead-code finder:

```toml
[[surfaces]]
id = "web"
garden = [["npx", "knip"]]
```

The weekly report-only workflow (`.github/workflows/garden.yml`) publishes the
report as a job summary. A `doc-gardener` or `implementer` subagent fixes
findings, one root cause per change (see [`delegation.md`](./delegation.md)).

## Scale and limits

- `make where` searches with `git grep` (falls back to a Python scan outside
  git) and skips files over 400 KB. Doc bindings are cached by size and mtime
  in ignored `.agent/cache/`, so the per-edit hook does not re-read every doc.
- Staleness inspects the newest 2000 non-merge commits; a document last
  committed before that window is not judged.
- The stop gate judges the whole branch, so an unresolved finding is raised
  once per turn until it is fixed or exempted by a trailer.
- Hooks, the git gate, and `make` run through `tools/repoctl`, which picks the
  newest Python 3.11+ on `PATH` even when `python3` is an older system
  interpreter (override with `REPOCTL_PYTHON` or `make PYTHON=...`). Windows
  hosts run it from Git Bash or WSL.

## Fixes reach every project: `make kit-update`

A template bug is copied into every project made from it, so fixes flow both
ways. `make init` and `make adopt` record `tools/kit-lock.json`, the hash of
every kit file as shipped (generated `repoctl:` blocks excluded, so regenerated
tables are not edits). `make kit-update [KIT=<template checkout>]` (default: a
fresh clone of `[template].source`) then, per kit file:

| State | What happens |
|---|---|
| unchanged since shipped | replaced by the template's new version |
| changed by the project, kit unchanged | kept, silently |
| changed by the project and by the kit | kept; the kit's version is saved under `.agent/kit-update/` and listed once to merge by hand |
| new in the template | added; if you already have your own file there, it is kept and listed once |
| removed from the template | deleted when unchanged, listed otherwise |
| your own file that `make adopt` kept at a kit path | never touched; listed only when the kit's version changes |

A conflict is reported once per kit change: the lock then remembers the version
offered, so the next update is quiet until the kit changes that file again. It
also remembers the version the project had from the kit before its edit
(`bases`): if the project later reverts the file to that version, the next
update applies the kit's version again instead of treating it as an edit. The
staged version stays in `.agent/kit-update/` and `make garden` lists it on every
run until you merge it and delete the staged file, so an ignored kit fix is never
silently lost. A
project made before the lock existed gets every differing kit file listed once
on its first update (nothing is overwritten); after that, updates apply
automatically. A kit checkout without git history keeps the recorded
`kit_version`, and an update from a lock that never recorded one says so
instead of printing a placeholder.

Project-owned files are never kit files: `project.toml`, `VISION.md`,
`README.md`, `LICENSE`, `CONTEXT.md`, the stack decision, design, architecture,
product, ADR, and incident docs, `.security/`, and generated host files.
Project make targets go in `project.mk`, which the kit Makefile includes, so the
Makefile stays the kit's (adopted projects keep `kit.mk`, regenerated with
their renames). Markdown is localized the same way `make init` does it. The
update refuses a dirty tree, so it lands as one reviewable change; run
`make done` after it. `make garden` reports when the template has moved past
the recorded `kit_version`.

The other direction: an agent that finds a kit bug in a project fixes it there
and reports it at `[template].source` (AGENTS.md), and the template's fix then
reaches every project through `make kit-update`. Tests prove that init or adopt
followed by an update from the same kit changes nothing, and that an update
applies fixes, additions, and removals while keeping the project's edits.

## The golden path is a test

A bug in the template is copied into every project made from it, so the happy
path is tested end to end in CI (`GoldenPathTests`): `make init`, a scripted
minimal intake (accepted vision and stack decision, owner, one real surface),
a fully green `make done` (which runs the kit's own suite inside the new
project), and a commit through the git gate. An accepted record that still has
placeholders must be refused. A template change that breaks any step fails the
template's CI before it reaches a project.

## Measuring the kit: fresh-agent evals

`.agents/evals/*.toml` holds navigation tasks with an expected-answer regex.
`make eval AGENT=claude` (or `codex`, `gemini`; `MODEL=` overrides, and Claude
defaults to the cheap `[kit].eval_model`, Haiku) runs each task in a fresh,
read-only headless session (without MCP servers, so runs stay fast and
deterministic) and records pass rate, turns, time, and cost under
`.agent/evals/`. Re-run it after changing `AGENTS.md`, the map, or the docs.
A change to the kit that lowers the pass rate or raises cost is a regression.
For changes to the skills or gates, also run a **build trial**:
`make trial NAME=<request>` copies this working tree into a fresh `make init`
project outside the repository (or, for `mode = "adopt"`, an existing codebase
from `seed` that then runs `make adopt`), gives `claude -p` (Sonnet by
default, `BUDGET=` caps spend) the owner's request from
`.agents/trials/<request>.toml`, and writes `.agent/trials/<run>/report.md`:
spend, turns, kit commands, every gate block, failed kit command, bypass, and
`Docs-Unaffected` trailer, and the product's final `make next` phase and
`make done` result. Judge each friction item with the blocking rule above: fix
the kit, make the check advisory, or justify it. `--analyze <transcript>
--project <dir>` reports on a run made by hand or with another host. The first
trial built a working prototype for $1.74 but skipped the design record, the
owning doc, and the UI review; those became the product guardrails above. A
second run told only to "run make done and fix what it reports" repaired all
five findings for $0.70. Visual review still needs a browser in the run.

The third trial (2026-10-07, issue #9) asked Sonnet for an ambitious product, a
collaborative offline-first trip planner, with the owner's answers up front. In
36 minutes and $22.81 it researched (marking unreachable pages
`[unverified]` instead of inventing quotes), wrote 28 feature rows, built a
4,300-line TypeScript app with 39 unit, API, and end-to-end tests, judged 32
screenshots, ran a critic, and fixed its blockers; `make done` was green. The
friction it hit became fixes, not new rules: five failed `make issue` runs on a
local draft (local drafts now need only an outcome and criteria), a review log
that failed the docs index until `make sync` (the review now syncs), and a
preemptive `Docs-Unaffected: tools/** untouched` that silently exempted every
doc (non-document scopes now exempt nothing). It never bypassed a gate. It
stopped with a stale UI review after its final fix, which `make next` reports
and `make readiness` enforces before release.

A host-side failure, such as an expired login, is recorded as an error rather
than as a wrong answer. Evals and trials start agents through one launcher
(`run_headless` in `tools/kit/evals.py`): it drops the launching session's host
variables, so a benchmark started from inside an agent session uses the CLI's
own login, as a truly fresh agent would, and it ignores `SIGTERM` while the
agent runs, because agents clean up with `pkill -f <name>`, which once killed
a trial's runner. Both commands belong to the `measure` pack.
