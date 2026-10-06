# AI_TEMPLATE

<!-- repoctl:description -->
Self-healing starting point for AI-agent-built projects of any size: docs bound to code, generated host adapters, delegation roles, and deterministic gates for any agent or model.
<!-- /repoctl:description -->

A starting point for any project built mostly by AI coding agents: website,
game, backend, native app, 3D or video pipeline, data product, documents, or
something new. It works with any agent host (Claude Code, Codex, Copilot,
Cursor, Gemini) and any model, because the rules that matter are **executed by
tools**, not remembered by the agent.

This is a technical starting point, not a promise of legal, security, privacy,
accessibility, or performance compliance. Those claims need project facts,
runtime evidence, and qualified review.

## Why

Agents are fast at the start of a project and sloppy at the end of a long
session: docs stop matching the code, replaced code is never deleted,
navigation goes stale, and the next session starts blind. In a large codebase
that compounds until every bug fix is archaeology. This template turns the
upkeep into deterministic checks and hooks, so the repository heals itself and
any agent can pick it up cold.

## Start a project

<!-- repoctl:quickstart -->
```bash
# Click "Use this template" on GitHub (or clone), then in the new repository:
make init NAME=my-project KIND=web   # identity, pending vision, prunes template-only files
make start                            # session brief; installs the git commit gate
make check                            # everything green before the first change
```
<!-- /repoctl:quickstart -->

Then complete `VISION.md` and `docs/STACK-DECISION.md`, declare your first real
surface in `project.toml`, and let `make doctor` show the remaining gates.
`make init` never invents folders or picks a framework for you.

<!-- repoctl:project-readme -->
> Project initialized: **AI_TEMPLATE** (`template`). Keep this identity,
> launch state, and project-specific quick start current.

## How it stays healthy

| What goes wrong in agent-built codebases | What this template does about it |
|---|---|
| Docs drift from the code | Docs declare `<!-- covers: -->` paths; stale or dead bindings fail `make check`, and the git commit gate and agent stop hook refuse changes that skip the owning doc. |
| Replaced code lingers as duplicates | `DEPRECATED(remove-by=YYYY-MM-DD)` markers fail after their date; task markers need an issue; `make garden` reports duplicated prose and every rot finding weekly. |
| Context is lost between sessions | Session hooks (or `make start`) print a brief; a checkpoint is written before compaction; `make handover` pre-fills the next session's record. |
| Too much to read, too many places | `AGENTS.md` is a budgeted router loaded into every session; the docs index and host files are generated; `make where` finds code, owners, and past failures in one call. |
| One agent tries to hold everything | Six roles (scout, implementer, critic, researcher, doc-gardener, skill-scout) with a fixed brief and short reports keep the orchestrator's context for decisions. |
| Every agent host wants its own files | Skills, roles, and MCP routes have one canonical copy in `.agents/` and `resources.toml`; `make sync` generates content-free host adapters. |
| "Done" means "it compiled" | Risk tiers set the ceremony; an independent critic and the real artifact decide; `make eval` measures whether a fresh agent can still navigate. |

The mechanics are in [`docs/self-healing.md`](./docs/self-healing.md) and
[`docs/delegation.md`](./docs/delegation.md).

## Everyday commands

```bash
make start        # session brief (hosted agents get it automatically)
make where Q="checkout flow"   # paths, symbols, owning docs, past failures
make risk         # how much ceremony this branch's change needs
make done         # before saying "done": heal derived files, gates, all tests
make similar Q="release notes"                      # is there already a skill/role for this?
make new KIND=skill NAME=release-notes DESC="..."   # add a skill, agent role, or doc, wired in
make garden       # full rot report
make sync         # regenerate derived files after editing their sources
make help         # everything else
```

## Layout

| Path | Role |
|---|---|
| `AGENTS.md` | The operating contract and trigger router (imported by `CLAUDE.md` and `GEMINI.md`). |
| `project.toml`, `resources.toml` | Machine-readable truth: surfaces, checks, budgets, risk tiers, provenance, resource and MCP routes. |
| `.agents/` | Canonical skills, subagent roles, and the fresh-agent benchmark. |
| `.claude/`, `.mcp.json` | Generated host adapters; never edited by hand. |
| `docs/` | One owner document per concern; [`docs/README.md`](./docs/README.md) is the generated index. |
| `tools/` | `repoctl` (standard-library Python 3.11+) and its focused `kit/` modules. |
| `.githooks/`, `.github/` | The commit gate, CI, the weekly gardener, and issue forms. |

Live work, status, and acceptance evidence belong in GitHub Issues, never in a
Markdown backlog. See [`docs/ISSUE_TEMPLATE.md`](./docs/ISSUE_TEMPLATE.md) and
[`CONTRIBUTING.md`](./CONTRIBUTING.md).

## Requirements

Python 3.11+ and git. Optional: the GitHub CLI (`gh`) for issues and
`make github-sync`, and Node for the Playwright MCP route. Project toolchains
are declared per surface in `project.toml`.

## Before publishing a real project

Select a license, name accountable owners, configure branch protection and
secret scanning, replace legal placeholders with verified facts, and attach
runtime, provider, and counsel evidence to the launch issue. Start at
[`docs/production.md`](./docs/production.md).

The research behind these defaults is in the template repository
([baselines](./docs/research/agentic-repository-baselines.md)); `make init`
removes it from new projects and points this link at the template.
