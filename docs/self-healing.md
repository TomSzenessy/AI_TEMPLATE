# Self-healing mechanics

<!-- covers: tools/kit/docsync.py tools/kit/hygiene.py tools/kit/adapters.py tools/kit/session.py tools/kit/garden.py tools/kit/navigate.py tools/kit/risk.py tools/kit/capabilities.py tools/kit/evals.py tools/kit/gitinfo.py .github/workflows/garden.yml .agents/evals/** -->

Agents follow written rules well at the start of a session and worst at the end,
after compaction, which is when cleanup and documentation get skipped. So the
maintenance rules here are **executed**, not remembered: lifecycle hooks,
checks in `make check`, and a scheduled gardener. Every mechanism is a
standard-library command in `tools/kit/`, so it works with any agent host.

## Lifecycle (any host)

| Moment | Host with hooks | Host without hooks | What happens |
|---|---|---|---|
| Session start or resume | `repoctl hook session-start` | `make start` | Brief: branch, recent commits, `HANDOVER.md`, map, open self-healing findings. Drifted adapters are regenerated. |
| Before context compaction | `repoctl hook pre-compact` | — | Writes `.agent/checkpoint.md` (uncommitted paths, docs still owed). |
| After a file edit | `repoctl hook after-edit` | — | Names the docs covering the edited path (once per session); regenerates adapters when a canonical source changed; warns on edits to generated files. |
| Before declaring done | `repoctl hook stop` | `make finish` | Gate over this branch's change set: owed docs, adapter drift, dead bindings, expired or undated markers. Blocks once, then the agent fixes or explains. |

Claude Code receives the hooks through the generated `.claude/settings.json`.
Other hosts read [`AGENTS.md`](../AGENTS.md), which tells them to run the make
targets.

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
  (no path = all documents).
- **Owed document**: covered paths changed on this branch while the doc did not;
  the stop gate and `make finish` report it before history even exists.
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

## Context budgets

`project.toml [budgets]` maps globs to byte limits for files agents load often
(about 4 bytes per token). An over-budget file fails `make check`; move detail
into a linked owner document instead of growing the router.

## Host adapters

Canonical agent content lives in `.agents/` (skills, roles, evals) and
`resources.toml` (`[[mcp]]` routes). `make adapters` renders host files from it.
For Claude Code that means skill and role redirect stubs in `.claude/`,
`.claude/settings.json` (hooks and allowlisted kit commands; MCP servers stay approved per person),
and `.mcp.json`. Generated files hold no content of their own. `make check`
fails on drift or on any hand-written file in a host directory. Add a host by
adding a renderer in `tools/kit/adapters.py` and listing it in
`project.toml [adapters].hosts`. Codex, Copilot, and Cursor already read
`AGENTS.md` and `.agents/skills/` directly.

## Ceremony by risk

`make risk` classifies this branch's changed paths with `project.toml [risk]`
globs: `low` needs `make check` only, `normal` follows the full build and repair
loop (with a critic for subjective or commandless work), and `high` (CI, tooling, agent instructions, security, auth, and migrations by default) adds an
independent critic. Tune the globs per project. Never widen `low` to dodge a gate.

## The gardener

`make garden` aggregates every finding above plus advisory items (upcoming
deprecations, unbound docs, skill reviews older than a year) and runs each
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
- Generated hooks call `python3` via `$CLAUDE_PROJECT_DIR`, so Windows hosts
  need Python 3.11+ on `PATH` under that name (Git Bash or WSL).

## Measuring the kit: fresh-agent evals

`.agents/evals/*.toml` holds navigation tasks with an expected-answer regex.
`make eval AGENT=claude` (or `codex`, `gemini`) runs each task in a fresh,
read-only headless session (without MCP servers, so runs stay fast and
deterministic) and records pass rate, turns, time, and cost under
`.agent/evals/`. Re-run it after changing `AGENTS.md`, the map, or the docs.
A change to the kit that lowers the pass rate or raises cost is a regression.
A host-side failure, such as an expired login, is recorded as an error rather
than as a wrong answer. Runs drop the launching session's host variables, so a
benchmark started from inside an agent session uses the CLI's own login, as a
truly fresh agent would.
