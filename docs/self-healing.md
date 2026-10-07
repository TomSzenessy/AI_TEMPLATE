# Self-healing mechanics

<!-- index: operate | Hooks, doc-code bindings, deprecation expiry, budgets, generated files, gardener, evals | A check fails, docs drift, a host is added, or the kit itself changes. -->
<!-- covers: tools/kit/docsync.py tools/kit/hygiene.py tools/kit/adapters.py tools/kit/session.py tools/kit/garden.py tools/kit/navigate.py tools/kit/risk.py tools/kit/capabilities.py tools/kit/evals.py tools/kit/gitinfo.py tools/kit/derive.py tools/kit/scaffold.py tools/kit/config.py .githooks/** .github/workflows/garden.yml .agents/evals/** -->

Agents follow written rules well at the start of a session and worst at the end,
after compaction, which is when cleanup and documentation get skipped. So the
maintenance rules here are **executed**, not remembered: lifecycle hooks,
checks in `make check`, and a scheduled gardener. Every mechanism is a
standard-library command in `tools/kit/`, so it works with any agent host.

## Lifecycle (any host)

| Moment | Host with hooks | Host without hooks | What happens |
|---|---|---|---|
| Session start or resume | `repoctl hook session-start` | `make start` | Brief: branch, recent commits, `HANDOVER.md`, map, the `make next` step, open self-healing findings. Derived files are regenerated and the git commit gate is installed. |
| Before context compaction | `repoctl hook pre-compact` | — | Writes `.agent/checkpoint.md` (uncommitted paths, docs still owed). |
| After a file edit | `repoctl hook after-edit` | — | Names the docs covering the edited path (once per session); regenerates derived files when a source changed; warns on edits to generated files. |
| Before declaring done | `repoctl hook stop` | `make done` | Gate over this branch's change set: owed docs, derived-file drift, dead bindings, expired, undated, or unfinished markers, and UI surfaces without a fresh, judged `make ui-review` ([`building.md`](./building.md)); `make done` also prints product completeness. The hook blocks once; `make done` also runs every test. |
| Every commit | `.githooks/commit-msg` (any agent or human) | same | Refuses a commit whose staged covered code skips its doc (unless the message carries a `Docs-Unaffected:` trailer), plus marker checks, and derived-file drift when the commit touches a source. Exit 3 means blocked; a crashed kit never blocks a commit. Bypass deliberately with `--no-verify`. |

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
  (a reason with no path exempts all documents). Git's own trailer parsing is
  used everywhere: trailers belong in the message's last paragraph, and a
  trailer without a reason exempts nothing.
- **Owed document**: covered paths changed on this branch while the doc did not;
  the stop gate and `make done` report it before history even exists.
- **Command references**: every backticked `make <target>` or `repoctl <command>`
  in Markdown, and every `make` line in a code fence, must exist.

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

## Product guardrails

Steps a fresh agent skipped in a real build trial are checks, each naming its fix:

- A tracked backlog (`docs/*WAL*.md`, `TODO.md`, `BACKLOG.md`, `TASKS.md`,
  `ROADMAP.md`) fails: live work goes to issues, or to ignored `.agent/wal/`
  (`make issue` writes it there when the repository has no GitHub remote).
- Every active product surface needs an owning doc: some `<!-- covers: -->`
  binding must match files under its path.
- In a UI project (`[kit].ui_kinds`, by `project.toml` kind) an accepted vision
  requires `docs/design.md`, and each surface's `quality_oracle` must name the
  `ux-quality` screenshot review.
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
| `.mcp.json` | `resources.toml` `[[mcp]]` routes (servers are still approved per person) |
| The tables in [`README.md`](./README.md) | each document's `<!-- index: group \| owns \| read when -->` line |
| The role table in [`delegation.md`](./delegation.md) | role frontmatter (`description`, `access`, `tier`) |
| The description block in the root `README.md` | `project.toml [repository].description` |
| GitHub description, topics, template flag (`make github-sync`) | `project.toml [repository]`; `make garden` reports drift |

`make check` fails on any drift and on hand-written files in a generated host
directory. Add a host by adding a renderer in `tools/kit/adapters.py` and
listing it in `project.toml [adapters].hosts`. Codex, Copilot, and Cursor read
`AGENTS.md` and `.agents/skills/` directly.

## Extending: skills, roles, docs

`make similar Q="<need>"` answers first: reuse (score at or above
`[kit].overlap_limit`), read the closest match first (at or above half of it),
or create. `make new KIND=skill|agent|doc NAME=<kebab> DESC="<what>; <when>"` is
the one way to add a capability. It refuses a near-duplicate by description
and name (`FORCE=1` overrides), writes valid frontmatter or
index metadata, registers a first-party skill in `[capabilities].local_skills`,
regenerates every derived file, and leaves `FILL-IN:` lines for the content.
Refining an existing capability is an ordinary edit of its canonical file;
the after-edit hook regenerates what depends on it. Agent-instruction paths are
`high` risk, so changes to them get a critic.

## Configuration

Policy a project may change lives in `project.toml`, with built-in defaults
when a key is absent: `[kit]` (docs index groups, unbound-doc exemptions,
overlap limit, deprecation warning window, skill review age, UI project kinds,
eval model, Playwright version for `make ui-review`), `[adapters.claude]`
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

## The gardener

`make garden` aggregates every finding above plus advisory items (upcoming
deprecations, paragraphs repeated across documents, unbound docs, skill
reviews older than a year, GitHub metadata drift) and runs each
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

## Measuring the kit: fresh-agent evals

`.agents/evals/*.toml` holds navigation tasks with an expected-answer regex.
`make eval AGENT=claude` (or `codex`, `gemini`; `MODEL=` overrides, and Claude
defaults to the cheap `[kit].eval_model`, Haiku) runs each task in a fresh,
read-only headless session (without MCP servers, so runs stay fast and
deterministic) and records pass rate, turns, time, and cost under
`.agent/evals/`. Re-run it after changing `AGENTS.md`, the map, or the docs.
A change to the kit that lowers the pass rate or raises cost is a regression.
For changes to the skills or gates, also run a **build trial**: give a
cheap model (`claude -p --model sonnet`) a product request with the owner's
answers in a fresh `make init` copy, then audit what it skipped. The first
trial built a working prototype for $1.74 but skipped the design record, the
owning doc, and the UI review; those became the product guardrails above. A
second run told only to "run make done and fix what it reports" repaired all
five findings for $0.70. Visual review still needs a browser in the run.

A host-side failure, such as an expired login, is recorded as an error rather
than as a wrong answer. Runs drop the launching session's host variables, so a
benchmark started from inside an agent session uses the CLI's own login, as a
truly fresh agent would.
