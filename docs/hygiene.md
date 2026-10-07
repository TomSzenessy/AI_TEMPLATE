# Code and files that justify themselves

<!-- index: operate | Deprecation markers, orphan files, change coupling, and product guardrails | Code or files look stale, duplicated, or ownerless. -->
<!-- covers: tools/kit/hygiene.py tools/kit/reachability.py tools/kit/coupling.py -->

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

- `orphan-files` **advises** on a tracked file that nothing reaches: no
  document's `covers:` glob claims it, `make sync` does not generate it, and no
  code imports or names it. Every message says why the file may still be
  legitimate (a test tree a runner discovers, a `migrations/` or `management/`
  tree a framework walks, a `module:callable` or `path:line` reference) and
  names the fix for the rest — import it, bind it, or delete it. Advice, not a
  block: the honest claim is only "nothing in this tree names this file", the
  former blocking class proved wrong in each new ecosystem it met (a bare
  `src/`, `module:callable`, an adopted project's own `tools/`), and a wrong
  block is permanent in a project that has no upgrade path. A name two files
  share resolves to neither, so one stray mention of `index.py` cannot mask a
  dead file.
- Kit artifacts are exempt by default, from a list built out of the kit's own
  constants (`tools/kit/reachability.py`), so a project never has to justify a
  file the kit itself wrote.
- `host-read-config` **advises** on files only a host convention reads (editor,
  git, hosting, scanner config), for the same reason.

## Structure you can see

- `change-coupling` **advises**, from recent git history, when two areas keep
  changing together. That is what a wrong seam looks like over time, and it is a
  judgement, so it never blocks.

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
