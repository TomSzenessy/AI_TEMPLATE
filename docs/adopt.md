# Adopting an existing repository

<!-- index: operate | `make adopt`: what it merges, renames, and keeps in an existing repository | Bringing the kit into a repo that already has files. -->
<!-- covers: tools/kit/adopt.py -->

`make -f <kit>/Makefile adopt NAME=... KIND=... OWNER=...`, run from a clean
working tree of the existing repository, copies the kit in and then runs the
same initialization as `make init`. It never overwrites a file the project
owns:

| Collision | What adopt does |
|---|---|
| `Makefile` | Kit targets go to `kit.mk`, included at the end of your Makefile so your default goal stays; a kit target you already define is renamed `kit-<name>` (for example `kit-test`) everywhere in `kit.mk`, and `make sync` keeps the same renames when it regenerates the command block. Every kit-authored mention follows the rename (`make start` becomes `make kit-start` in kit Markdown/TOML prose, the session brief, and the generated Claude allowlist), all read from one table: your Makefile defines `<name>` and `kit.mk` defines `kit-<name>` (`kitlock.renamed_targets`). `make kit-update` renders prose the same way. An explicit `[adapters.claude] allow` is yours and used verbatim. |
| `AGENTS.md` | Merged, not kept: the kit router first (including the `repoctl:rules` block), your file verbatim beneath it under a `Project contract` heading between `repoctl:adopted-agents` markers (nothing is dropped). `project.toml` `[budgets]` for `AGENTS.md` is raised to fit, and adopt says so. The lock records the merge (`merged`), so `make kit-update` refreshes only the router part ([`kit-update.md`](./kit-update.md)). |
| A kit file that differs from one of yours only by case (`docs/CAPABILITIES.md` vs the kit's `docs/capabilities.md`) | Detected on every filesystem (lowercased paths against your tracked files) and reported as `case collision`, never as "kept yours" and never recorded as the kit's. Where the filesystem is case-sensitive the kit file is installed under its own name beside yours; on a case-insensitive one (macOS, Windows) it is saved as `kit-<name>` (for example `docs/kit-capabilities.md`), adopt names it, and the lock's `moved` table lets `make kit-update` keep refreshing it there. Links to the kit's name resolve to your file on such a filesystem. |
| `.gitignore` | Missing kit lines are appended under `# Agent kit`. |
| `README.md` | Your README stays; the project identity block is appended. |
| `docs/README.md` | Your page stays; the generated documentation index is appended. |
| `.github/workflows/<name>` | The kit's workflow is written beside yours as `kit-<name>`. |
| `LICENSE` | Yours is kept and the manifest's `license` label follows it. With none, the kit's is **not** copied (a license is your legal choice): no LICENSE file, `license = "UNSELECTED"`, and adopt says so. |
| anything else | Yours is kept. Kept files are recorded in `tools/kit-lock.json` as yours, so `make kit-update` never touches them and mentions one only when the kit's version of it changes. |

## Kit CI and your toolchains

The adopted `kit-ci.yml` installs only Python, so it cannot run a surface that
needs Node, Go, or any other toolchain (that was exit 127, `vitest: not found`).
It therefore calls `repoctl ci gate`, which in a project with
`[kit].project_mode = "adopt"` runs only the toolchain-free `repoctl check`
(structure, docs, issue contracts); the template and `make init` projects keep
the full `make verify`. Your surfaces' own tests belong to your project's CI,
with the toolchains it installs; `make adopt` prints this reminder. `make
verify` and `make done` still run the surfaces locally.

The Python the gate and the Makefile use is the one the environment configured:
an explicit `PYTHON=`, else `python3` when it is 3.11 or newer (what
`setup-python` puts first), else the newest `python3.N` that is. So the 3.11
matrix job really runs 3.11, and code needing a newer Python fails it
(`tools/tests/test_ci_gate.py`).

Template-only material is pruned exactly as `make init` prunes it: links to
it point at the template source and doc bindings to it are dropped. Your
existing `docs/*.md` get an `<!-- index: -->` line from their title (edit
the wording). Afterwards `make check` lists your code as unregistered surfaces:
declare each one in `project.toml` (or list support folders such as tests in
`[repository].infrastructure_paths`), then follow `make next`. When a file
belongs to a surface you already declared but sits outside that surface's
directory — the root `index.html` a Vite app keeps beside its `src/` — list it in
that surface's `extra_paths` rather than declaring a second surface for one file.
`make adopt` also records `[kit].project_mode = "adopt"`, so `make next` scopes a
feature delta from your code instead of opening with competitor research
([`building.md`](./building.md)); `make init` records `"new"`.
A document's
`make <target>` references resolve to the nearest Makefile above it, so
subprojects keep their own targets. What changed in `bootstrap.py`/`adopt.py`
last: the kit's file list now comes from `core.repository_files` (git-known
files only, links excluded), `KIND=` validation shares `core`'s kebab-case
pattern, and `adopt` passes the adopted mode to `initialize_project` —
internal consolidation and one recorded fact, same gate behaviour.
