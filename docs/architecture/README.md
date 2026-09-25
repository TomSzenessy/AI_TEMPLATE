# Architecture and decisions

This directory owns the current structural truth. Keep it short and factual;
put rationale for a hard-to-reverse trade-off in an ADR, not in every paragraph.

## Current map

Maintain one table when the project has more than one surface:

| Surface | Path | Owner | Interface / entry point | Quality oracle | Verification |
|---|---|---|---|---|---|
| _Add real surfaces after initialization._ | — | — | — | — | — |

`project.toml` is the machine-readable source for paths and commands. This table
is the human navigation view, not a second command catalog.

## Design rules

- A surface is independently owned, deployable or consumable, and verifiable.
- A module is deep when a small interface hides meaningful complexity. Put the
  seam where a caller, test, or adapter naturally crosses it.
- Keep product vocabulary in [`../../CONTEXT.md`](../../CONTEXT.md).
- Put stable rationale in [`../adr/`](../adr/README.md) only when the decision is
  hard to reverse, surprising without context, and based on a real trade-off.
- Put live work and status in GitHub Issues. Do not add a roadmap matrix here.
- Update the manifest, this map, and affected verification in the same change.

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
