# Fixes reach every project: `make kit-update`

<!-- index: operate | The kit lock, make kit-update, and the golden-path test | A kit fix must reach projects, or a project updates from the template. -->
<!-- covers: tools/kit/kitupdate.py -->

A template bug is copied into every project made from it, so fixes flow both
ways. `make init` and `make adopt` record `tools/kit-lock.json`, the hash of
every kit file as shipped (generated `repoctl:` blocks excluded, so regenerated
tables are not edits). `make kit-update [KIT=<template checkout>]` (default: a
fresh clone of `[template].source`, at `KIT_REF=<commit or tag>` when given,
printing the commit range it applies) then, per kit file:

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
