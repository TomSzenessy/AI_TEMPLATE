# Architecture and decisions

<!-- index: design | Current structure, seams, kit module map, and design rules | Adding a surface, changing dependencies, or locating ownership. -->
<!-- covers: tools/repoctl.py tools/kit/__init__.py tools/kit/core.py tools/kit/structure.py Makefile -->

This directory owns the current structural truth. Keep it short and factual;
put rationale for a hard-to-reverse trade-off in an ADR, not in every paragraph.

## Current map

Maintain one table when the project has more than one surface:

| Surface | Path | Owner | Interface / entry point | Quality oracle | Verification |
|---|---|---|---|---|---|
| _Add real surfaces after initialization._ | — | — | — | — | — |

`project.toml` is the machine-readable source for paths and commands. This table
is the human navigation view, not a second command catalog.

## Repository kit

`tools/repoctl.py` is only the command router; the `Makefile` exposes it as
`make` targets. Behavior lives in standard-library modules under `tools/kit/`
whose imports point toward `core`:

| Concern | Modules | Owner doc |
|---|---|---|
| Manifest, paths, worktree, text primitives | `core`, `gitinfo` | this page |
| Surfaces, vision, inventory, declared verification | `structure`, `bootstrap` | [`../ADAPTATION.md`](../ADAPTATION.md) |
| Issues, review packets, incidents, GitHub CLI | `issues`, `github` | [`../ISSUE_TEMPLATE.md`](../ISSUE_TEMPLATE.md) |
| Skills provenance, resource registry | `skills` | [`../skills.md`](../skills.md) |
| Links, index, file hygiene | `docs` | [`../security.md`](../security.md) |
| Launch evidence | `launch` | [`../production.md`](../production.md) |
| Self-healing: bindings, markers, derived files, scaffolding, hooks, garden, map, risk, config, evals | `docsync`, `hygiene`, `adapters`, `derive`, `scaffold`, `session`, `garden`, `navigate`, `risk`, `config`, `capabilities`, `evals` | [`../self-healing.md`](../self-healing.md) |

For a copied project, replace the template row above with the real surfaces
and keep this section only while the kit is part of the repository.

## Design rules

- A surface is independently owned, deployable or consumable, and verifiable.
- A module is deep when a small interface hides meaningful complexity. Put the
  seam where a caller, test, or adapter naturally crosses it.
- Keep product vocabulary in [`../../CONTEXT.md`](../../CONTEXT.md).
- Put stable rationale in [`../adr/`](../adr/README.md) only when the decision is
  hard to reverse, surprising without context, and based on a real trade-off.
- Put live work and status in GitHub Issues. Do not add a roadmap matrix here.
- Update the manifest, this map, and affected verification in the same change.
- At scale, enforce boundaries mechanically: declare an import or dependency
  rule checker (import-linter, dependency-cruiser, or a language equivalent)
  as a surface verification command so layering cannot erode silently.
- Give every non-trivial module a short card (purpose, public interface,
  invariants, owner, performance budget) bound with `<!-- covers: -->`, so
  agents load the card instead of the implementation.

## Architecture review prompts

Use these only when the trigger applies:

- Which module owns the behavior, and can its interface be made smaller?
- What changes if the storage, provider, renderer, or transport is replaced?
- Which facts are duplicated across code, config, docs, and tests?
- Which dependency direction is accidental?
- What is the smallest reproducible proof that the seam works?
- What can be deleted without leaving a dangling contract?

Record confirmed answers in the owning document; file independent improvements
as issues rather than expanding this page.
