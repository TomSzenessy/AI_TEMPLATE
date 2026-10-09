# Project adaptation

<!-- index: operate | Lean core, artifact lifecycle, packs, and capability patterns | Turning the template into a project without generating unnecessary structure. -->
<!-- covers: tools/kit/bootstrap.py tools/kit/adopt.py tools/kit/ci.py .github/workflows/ci.yml Makefile tools/repoctl -->

The template is a small kernel plus switchable packs (`.agents/packs/`;
[`[packs]` switching rules](./capabilities.md)), not a universal application scaffold. `make init`
starts a project from each pack's declared default. The kernel stays responsible for navigation, the project
manifest, issue-backed intent, path safety, declared verification, and bounded
review. Project-specific policy and code are added only after the vision intake
identifies a real need.

## Artifact lifecycle

The template contains deliberate scaffolds. Their lifecycle is part of keeping
a project small:

| Artifact | Keep/update | Replace or remove when |
|---|---|---|
| `VISION.md` | `make init` writes a fresh pending record whose REQUIRED placeholders block acceptance until the intake fills them. | Never remove; revise it when the product direction changes. |
| `docs/STACK-DECISION.md` | Keep the accepted decision and its rationale. | Replace a superseded decision with a new record or explicit revision. |
| `project.toml` example comments | Useful while adapting. | Remove unused examples/comments once the real manifest is understood. |
| `[[surfaces]] id = "template-bootstrap"` | Created by `make init` as a visible pending declaration, not a product check. | Replace it with the first real surface; never treat its governance check as product evidence. |
| `docs/handoffs/TEMPLATE.md` | Keep the one handover schema (`make handover` fills it). | Delete ignored `HANDOVER.md` after a session; keep a committed handoff only while another actor needs it. |
| `docs/ISSUE_TEMPLATE.md` and `.github/ISSUE_TEMPLATE/` | Keep as `agent-first` intake schemas. | Do not turn them into a status board; remove/disable native forms in `regulated` or `minimal` profiles. |
| `docs/legal/*.template.md` | Keep while a document may apply. | Replace with a reviewed final document and update `legal_document_paths`; unused templates may be removed from a project copy. |
| `docs/research/` | Keep as provenance while its guidance matters. | Archive/remove after the knowledge has been internalized and no decision cites it. |
| `tools/kit-lock.json` | Written by `make init`, `make adopt`, and `make kit-update`: what the project got from the kit. | Never edit by hand; `make kit-update` maintains it; `KIT_REF=<sha>` pins an update to one template commit instead of its HEAD ([`kit-update.md`](./kit-update.md)). |
| `project.mk` | Your own make targets; the kit Makefile includes it. | Keep project targets here, not in the kit's Makefile. |
| `.agents/trials/` | Template maintenance: build-trial requests and seeds. | Pruned by `make init` and skipped by `make adopt`, together with any doc binding that only pointed at them; add your own requests to run `make trial`. |
| `docs/ERROR_LOG.md` | Keep as an append-only solved-failure ledger. | Do not use it for open work; link open work to Issues. |
| `.agents/skills/` | Keep the small first-party workflows and verified reusable capabilities. | Retain a reviewed skill while it remains trusted and useful; remove it only with a documented trust, permission, maintenance, or owner decision. |
| `.security/` | Keep and refresh the threat model/config as security surfaces change. | Do not delete security evidence merely to make a check quiet. |
| `resources.toml` | Keep as the small read-only route registry. | Add or retire a route only with an owner, source/trust review, and current-use rationale. |
| `docs/production.md` | Keep as the generic release evidence boundary. | Replace its empty project-specific evidence with real records; do not turn it into a status board. |

A project should be able to remove unused optional material without removing
its operating contract, history, or evidence.

## Adopting an existing repository

`make -f <kit>/Makefile adopt NAME=... KIND=... OWNER=...`, run from a clean
working tree of the existing repository, copies the kit in and then runs the
same initialization as `make init`. It never overwrites a file the project
owns:

| Collision | What adopt does |
|---|---|
| `Makefile` | Kit targets go to `kit.mk`, included at the end of your Makefile so your default goal stays; a kit target you already define is renamed `kit-<name>` (for example `kit-test`) everywhere in `kit.mk`, and `make sync` keeps the same renames when it regenerates the command block. |
| `.gitignore` | Missing kit lines are appended under `# Agent kit`. |
| `README.md` | Your README stays; the project identity block is appended. |
| `docs/README.md` | Your page stays; the generated documentation index is appended. |
| `.github/workflows/<name>` | The kit's workflow is written beside yours as `kit-<name>`. |
| `LICENSE` and anything else | Yours is kept; the manifest's `license` label follows your LICENSE. Kept files are recorded in `tools/kit-lock.json` as yours, so `make kit-update` never touches them and mentions one only when the kit's version of it changes. |

### Kit CI and your toolchains

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

## Adaptation loop

1. Read `VISION.md`, `docs/STACK-DECISION.md`, and the active surfaces.
   Name the accountable owner at init (`make init ... OWNER=<handle>`) or in
   `project.toml` `owners`; the `project-owner` placeholder fails `make check`.
2. If `make init` created `template-bootstrap`, replace it with the first real
   surface before treating verification as product evidence.
3. Run `make inventory` and classify each candidate as product, infrastructure,
   generated output, or unresolved. A top-level directory is a candidate only
   when git lists at least one tracked or untracked-but-not-ignored file under
   it, so a directory holding only ignored caches (such as a leftover `.gocache`)
   is not reported.
   Test and example folders (`tests/`, `test/`, `e2e/`, `__tests__/`, `spec/`,
   `fixtures/`, `examples/`, `test-results/`, `playwright-report/`) count as
   infrastructure by default; ambiguous ones such as `scripts/` or `config/`
   need a surface or an `[repository].infrastructure_paths` entry.
4. Ask the owner only for choices that change product direction, data/security
   boundaries, deployment, cost, or an irreversible dependency. The
   `product-kickoff` skill bundles these into one round of questions with
   recommendations and shows mockups before any code.
5. Record the decision and acceptance evidence in the issue/WAL.
6. Add only the smallest surface, toolchain, and verification needed for the
   first real artifact. A single-file product may declare `kind = "file"`,
   `"script"`, `"document"`, or `"asset"` and point at the file; directory
   surfaces remain the default.
7. Re-run inventory and the declared checks; remove or deprecate anything with
   no owner, oracle, or caller.

## Capability patterns by product type

These are discoverable patterns, not files copied into every project:

- **Web/app:** framework decision record, browser/artifact oracle, accessibility
  and privacy boundaries when applicable.
- **Game:** deterministic scenario, saved-state/performance trace, playable
  artifact.
- **Backend/data:** schema/migration, request/state proof, retention/deletion and
  provider boundaries.
- **Native:** platform/toolchain, device/emulator evidence, packaging/signing.
- **Media/3D:** pinned renderer/encoder, reproducible export, frame/waveform or
  playback inspection, storage/LFS policy for large source media.
- **Regulated/public launch:** counsel/provider evidence, privacy inventory,
  disclosure route, and runtime proof. Keep these gates external and explicit;
  no template text certifies compliance.
- **Reference-product work:** the reviewed `.agents/skills/` recon/parity/
  design-token/review-mining/brand-sweep pack owned by [`skills.md`](./skills.md).

A pattern is activated by adding its project-specific surface, commands, and
records to `project.toml` and the documentation index. When it earns reusable
capabilities, group them as a pack (`make new KIND=pack`, then `PACK=<name>` on
each `make new`) so another project can switch them on or off in one line. The
kernel does not generate framework folders or install a skill before a trigger
exists.
