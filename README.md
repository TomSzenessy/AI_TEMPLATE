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
make init NAME=my-project KIND=web OWNER=your-handle   # identity, owner, pending vision; prunes template-only files
make start                            # session brief; installs the git commit gate
make check                            # everything green before the first change
```
<!-- /repoctl:quickstart -->

Then tell your agent what to build. It runs the `product-kickoff` skill first:
one round of questions with recommendations (users, platforms, stack such as
Next.js + Tailwind, Expo, Flutter, or SwiftUI, visual style), two or three
mockup directions to choose from, and the decisions recorded in `VISION.md`,
`docs/STACK-DECISION.md`, and `docs/design.md`, plus a list of issues, each one
a slice of the product that runs end to end. The `stack-foundation` skill then
builds a deployed minimal version that runs (a *walking skeleton*: the thinnest
thing that works) with strict types, lint, tests, CI, previews, and error
tracking; UI work follows the `ux-quality` skill and gets screenshot reviews.
`make init` itself never invents folders or picks a framework for you.

### Already have a codebase?

Bring the kit to it instead of starting from the template. The *kit* is the
shared tooling every project built this way keeps: the `Makefile` targets, the
Python in `tools/`, the git hooks, and the files under `.agents/` that say what
agents may do. `make adopt` copies it in beside your own files.

```bash
git clone https://github.com/TomSzenessy/AI_TEMPLATE ../agent-kit
make -f ../agent-kit/Makefile adopt NAME=my-app KIND=web OWNER=your-handle
```

`make adopt` never overwrites your files: the targets go to `kit.mk` (included
from your Makefile, with any target you already define renamed `kit-<name>`),
your README, licence, docs, and workflows stay yours, and the kit's pieces are
merged in beside them ([`docs/ADAPTATION.md`](./docs/ADAPTATION.md#adopting-an-existing-repository)).

<!-- repoctl:project-readme -->
> **Template mode:** you are reading the template itself, not a project built
> from it. The first command in "Start a project" above turns this repository
> into your project, deletes the template-only files, and rewrites this block
> with your own project's name and kind.
<!-- /repoctl:project-readme -->

## How it stays healthy

| What goes wrong in agent-built codebases | What this template does about it |
|---|---|
| Docs drift from the code | Docs declare `<!-- covers: -->` paths; stale or dead bindings fail `make check`, and the git commit gate and agent stop hook refuse changes that skip the owning doc. |
| Replaced code lingers as duplicates | `DEPRECATED(remove-by=YYYY-MM-DD)` markers fail after their date; a `TODO` comment must name an issue; `make garden` reports duplicated prose and every sign of decay weekly. |
| Context is lost between sessions | Session hooks (or `make start`) print a brief; a checkpoint is written before the agent host shrinks an old conversation to save space; `make handover` pre-fills the next session's record. |
| Too much to read, too many places | `AGENTS.md` is a short rulebook loaded into every session (a byte budget keeps it short); the docs index and host files are generated; `make where` finds code, owners, and past failures in one call. |
| One agent tries to hold everything | Six roles (scout, implementer, critic, researcher, doc-gardener, skill-scout) with a fixed brief and short reports keep the agent in charge free to decide. |
| Every agent host wants its own files | Skills, roles, rules, and MCP routes (a connection to an outside tool, over the Model Context Protocol) have one real copy in `.agents/`; `make sync` writes each agent tool's own files from it. |
| The system cannot grow without losing its shape | Each of the eight kinds -- skill, agent role, doc, rule, check, command, MCP route, pack -- is one file added by `make new`, found by `make where` and `make similar`; a pack is a named group of them that stays out of context until it is switched on. |
| "Done" means "it compiled" | `make risk` says how much review a change needs (see below); an independent critic and the real artifact decide; `make eval` measures whether a fresh agent can still find its way around. |

The mechanics are in [`docs/self-healing.md`](./docs/self-healing.md) and
[`docs/delegation.md`](./docs/delegation.md).

## Everyday commands

Every command is a `make` target that runs the Python tool in `tools/`. The
list below is printed by `make help` and written here by `make sync` from the
same declarations, so the two can never disagree; editing this block by hand
fails `make check`.

Three words are used throughout the tools, so here they are first:

- A **capability** is one file that adds exactly one thing to the repository: a
  `skill` (repeated instructions an agent follows), an `agent` (a delegated role
  with its own access level and model choice), a `doc` (an owned document under
  `docs/`), a `rule` (one instruction agents must obey), a `check` (a test the
  tools run), a `command` (a new `make` target), an `mcp` route (a connection to
  an outside tool the agent may call, over the Model Context Protocol), or a
  `pack` (a named group of these that stays switched off until you turn it on).
- **Ceremony** is how much review and evidence a change needs: `low`, `normal`,
  or `high`. It follows where the change lands, not how many lines it touches.
- The **kit** is the shared tooling this repository ships and every project
  keeps: `tools/`, the `Makefile` targets, the git hooks, and `.agents/`.

<!-- repoctl:commands -->
```bash
EVERY SESSION (this is all most tasks need)
  make start                         Print the session brief: branch, handover, map, next step, what needs attention
  make next                          The single next step toward a complete product
  make where Q="login form"          Find files, symbols, owning docs, rules, capabilities, and past failures
  make ui-review                     Screenshot the UI (phone/desktop, light/dark) for a judged review
  make done                          Before saying "done": heal derived files, gates, all tests

EXTEND THE SYSTEM (one path for every kind of capability)
  make new KIND=skill|agent|doc|rule|check|command|mcp|pack NAME=x DESC="what; when"
                                     Create any capability with valid metadata and wire it in
  make similar Q="release notes"     Does a similar capability (any kind, any pack) already exist?
  make capabilities                  Every capability by kind and pack, plus tools, agent hosts, and MCP routes

WHEN NEEDED
  make risk                          How much ceremony this change needs (low, normal, high)
  make handover                      Write HANDOVER.md before pausing (git facts pre-filled)
  make map                           One-screen repository map
  make garden                        Full rot report: every check, advisory ones included
  make sync                          Regenerate derived files after editing their sources
  make issue BODY=path TITLE="..." TYPE=... PRIORITY=... AREA=... TOPIC=...
                                     Validate and file a duplicate-aware issue (or Local-WAL drafts)
  make review-packet ISSUE_FILE=path Print a fresh-agent critic brief for an issue
  make incident TITLE="..." SUMMARY="..."
                                     Create a private incident regression record

PROJECT SETUP AND MAINTENANCE
  make init NAME=my-project KIND=web [OWNER=you]
                                     Turn the template into your project
  make -f <kit>/Makefile adopt NAME=x KIND=web OWNER=you
                                     Bring this kit into an existing repository (--root) without overwriting it
  make kit-update [KIT=<template checkout>] [KIT_REF=<sha>]
                                     Pull template fixes into this project (keeps your changes)
  make check                         Every blocking check of the enabled packs
  make doctor                        Check initialization and the readiness of the declared phase
  make readiness                     Enforce public-launch evidence gates
  make inventory                     Show detected and declared product surfaces
  make resources                     Show the validated read-only resource router
  make skill-digest SKILL_PATH=.agents/skills/name
                                     Hash a reviewed skill directory for provenance
  make validate BODY=path            Validate a canonical issue body
  make labels                        Create or update the canonical GitHub issue labels
  make github-sync                   Apply project.toml description, topics, and template flag to GitHub
  make eval AGENT=claude [MODEL=haiku]
                                     Fresh-agent navigation benchmark (cheap model by default)
  make trial NAME=<request> [MODEL=sonnet] [BUDGET=25]
                                     Build trial: an agent builds a product from a request; friction report
  make verify                        Tests, every surface's verification, and doctor (CI runs this)
  make test                          The kit's and every skill's unit tests
  make test-future                   The suite 800 days ahead: catches checks that rot with the calendar
```
<!-- /repoctl:commands -->

**Once per session.** `make start` prints where you are: the branch, the last
handover note, a one-screen map of the repository, the single next step, and
anything that needs attention. It also installs the git commit gate.
`make where Q="checkout flow"` answers "where does this live?" with file paths,
code symbols, the document that owns each path, and past failures, so run it
before searching by hand. `make next` names the one step that moves a product
forward. `make done` is the gate before you call work finished: it rewrites the
generated files, runs the checks, and runs the tests.

**Before you edit.** `make risk` prints `low`, `normal`, or `high` -- the
ceremony this branch's change needs, decided from where the change lands.
`make sync` rewrites every file that is built from other files -- this command
list, the Makefile targets, the documentation index -- so run it after editing
whatever feeds them, or the commit gate refuses the change.

**When you add something to the repository.** `make similar Q="release notes"`
searches every kind of capability before you write a duplicate. When nothing
similar exists, `make new KIND=... NAME=... DESC="what it does; when to use it"`
writes that file with its metadata already wired in; `KIND` is one of the eight
kinds listed above (`repoctl new --help` prints them). `make capabilities` lists
everything the project already has.

**When something looks stale.** `make garden` runs every check, the advisory
ones included, and each finding names the fix that clears it. `make handover`
writes `HANDOVER.md` with the git facts filled in before you pause. `make map`
prints the repository map on its own.

**Before you file or hand off work.** `make issue` checks an issue body for
duplicates and files it on GitHub; with no remote configured it records it
locally as a `Local-WAL` (a write-ahead log: the issue is written down before
any code changes, so an interrupted session loses nothing).
`make review-packet ISSUE_FILE=path` prints a brief a fresh agent can judge the
work against.

## Layout

| Path | Role |
|---|---|
| `AGENTS.md` | The rules every agent session follows, plus a table that points to the right document for each kind of task (`CLAUDE.md` and `GEMINI.md` import it rather than repeat it). |
| `project.toml`, `resources.toml` | The facts the tools read instead of prose: which surfaces the project has, byte budgets, which changes count as risky, which groups of files are switched on, and which outside documents may be read. |
| `.agents/` | Everything you add to the project, one file each: skills, agent roles, rules, checks, commands, MCP routes, packs, and the fresh-agent benchmark. |
| `.claude/`, `.mcp.json` | Generated from `.agents/` for each agent tool; never edited by hand. |
| `docs/` | One owner document per concern; [`docs/README.md`](./docs/README.md) is the generated index. |
| `tools/` | `repoctl` (standard-library Python 3.11+) and the small focused modules it is split into. |
| `.githooks/`, `.github/` | The commit gate, CI, the weekly gardener, and issue forms. |

Live work belongs in GitHub Issues -- one issue per problem, carrying the
evidence that it was fixed -- not in a Markdown backlog on the side. See
[`docs/ISSUE_TEMPLATE.md`](./docs/ISSUE_TEMPLATE.md) and
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
