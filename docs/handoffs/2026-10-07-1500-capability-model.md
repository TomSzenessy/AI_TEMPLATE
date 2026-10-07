# Handoff — one capability model (#14) on top of PR #11

<!-- index: operate | Continuation record for the capability model branch (#14, #15) | Picking up feat/capability-model or reviewing it before a PR. -->

- **Created (UTC):** `2026-10-07T15:00Z`
- **Next actor/session focus:** the owner's own agent test (prompt below), then a PR stacked on PR #11.
- **Sharing boundary:** public repository (no secrets or personal data below)

## Objective

Make the template grow without losing its shape: every capability (skill,
agent role, doc, rule, check, command, MCP route, pack) is one file, created by
`make new`, found by `make where` and `make similar`, and switchable in packs,
so projects never edit kit files and `make kit-update` stays conflict-free.
The plan is frozen in [`../adr/0002-one-capability-model.md`](../adr/0002-one-capability-model.md).

## Current state

- **Committed baseline:** branch `feat/capability-model` (pushed to origin), on
  top of `claude/funny-ritchie-if635h` (PR #11): `5456732` (ADR), `28950a2`
  (implementation, closes #15), plus this record.
- **Done (verified):** `make done` green; `make test-future` green; 142 kit
  tests (9 new) and every skill suite pass; an independent critic (Sonnet)
  found no blocker.
- **Not run:** build trials (owner's decision, cost) and the three new
  navigation evals in `.agents/evals/navigation.toml` (`add-a-check`,
  `add-an-mcp-server`, `switch-off-a-pack`).

## Decisions and constraints

- Docs keep their `<!-- index: -->` line as their carrier; everything else uses
  frontmatter, TOML, or `@check`/`@command`. Same fields, one loader.
- Packs: `product` (on) and `measure` (off, on in the template). No `launch`
  pack: launch gates already switch on by `phase`.
- `init`, `adopt`, and `kit-update` stay separate commands; they already share
  their install steps (ADR 0002 says why).
- A third-party skill records its pack in `[[skills]]` provenance, because its
  files are pinned by digest.

## Blockers and open questions

- Another Claude Code desktop session had this checkout open during the work;
  the Makefile was reset to its committed version once (14:23) and was
  regenerated. A kit Makefile that loses its command block is now reported as
  drift. Run one session per checkout, or use worktrees.

## Exact next action

1. Run the owner's agent with the prompt in the PR description or the chat.
2. Push `feat/capability-model`, open a PR based on PR #11's branch, link #14.
3. After both PRs merge: run the evals (`make eval`, Haiku), tag `v0.1.0`, and
   delete this record and the PR #11 handoff.

## Relevant paths and issues

- Code: `tools/kit/registry.py`, `tools/kit/checks.py`, `tools/kit/commands.py`, `tools/repoctl.py`, `Makefile`.
- Docs: [`../capabilities.md`](../capabilities.md), [`../skills.md`](../skills.md), [`../resources.md`](../resources.md), [`../architecture/README.md`](../architecture/README.md).
- Issues: #14 (stays open until the PR merges and the evals pass), #15 (closed by `28950a2` on merge).

## Verified skill suggestions

none

## Redaction and retention check

No secrets, credentials, or personal data. Delete once the PR merges.
