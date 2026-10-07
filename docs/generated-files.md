# Generated files: one source each

<!-- index: operate | Derived files, host adapters, and generated blocks | A generated file looks wrong, or a new agent host is added. -->
<!-- covers: tools/kit/derive.py tools/kit/adapters.py tools/kit/helptext.py -->

Nothing that can be generated is maintained by hand. `make sync` (also run by
`make done`, the session-start hook, and the after-edit hook) renders:

| Derived | Single source |
|---|---|
| `.claude/skills/*`, `.claude/agents/*` (redirect stubs) | `.agents/skills/*/SKILL.md`, `.agents/agents/*.md` frontmatter |
| `.claude/settings.json` (hooks, pre-approved kit commands) | the kit, plus optional `project.toml [adapters.claude]` |
| `.mcp.json` | `.agents/mcp/*.toml` routes of enabled packs (servers are still approved per person) |
| The command block in the `Makefile` (`kit.mk` after `make adopt`) and `make help` | each `@command` declaration in `tools/kit/commands.py` and `.agents/commands/` |
| The project rules block in `AGENTS.md` | `.agents/rules/*.md` without a `scope` |
| The tables in [`README.md`](./README.md) | each document's `<!-- index: group \| owns \| read when -->` line (transient `docs/handoffs/` records are not indexed) |
| The role table in [`delegation.md`](./delegation.md) | role frontmatter (`description`, `access`, `tier`) |
| The description block in the root `README.md` | `project.toml [repository].description` |
| GitHub description, topics, template flag (`make github-sync`) | `project.toml [repository]`; `make garden` reports drift |

Generated host stubs cover only capabilities of enabled packs.
`make check` fails on any drift and on hand-written files in a generated host
directory. Add a host by adding a renderer in `tools/kit/adapters.py` and
listing it in `project.toml [adapters].hosts`. Codex, Copilot, and Cursor read
`AGENTS.md` and `.agents/skills/` directly.

A host entry file must *load* the router, not just point at it. `CLAUDE.md`
imports it with `@AGENTS.md`; a pointer-only file makes a fresh agent skip the
read (the benchmark that proved it is in
[#9](https://github.com/TomSzenessy/AI_TEMPLATE/issues/9)).
