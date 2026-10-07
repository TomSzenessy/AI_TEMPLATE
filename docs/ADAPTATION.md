# Project adaptation

<!-- index: operate | Lean core, artifact lifecycle, and capability-pack selection | Turning the template into a project without generating unnecessary structure. -->
<!-- covers: tools/kit/bootstrap.py tools/kit/adopt.py -->

The template is a small kernel plus capability packs, not a universal
application scaffold. The kernel stays responsible for navigation, the project
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
| `tools/kit-lock.json` | Written by `make init`, `make adopt`, and `make kit-update`: what the project got from the kit. | Never edit by hand; `make kit-update` maintains it ([self-healing](./self-healing.md#fixes-reach-every-project-make-kit-update)). |
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
| `Makefile` | Kit targets go to `kit.mk`, included at the end of your Makefile so your default goal stays; a kit target you already define is renamed `kit-<name>` (for example `kit-test`) everywhere in `kit.mk`. |
| `.gitignore` | Missing kit lines are appended under `# Agent kit`. |
| `README.md` | Your README stays; the project identity block is appended. |
| `docs/README.md` | Your page stays; the generated documentation index is appended. |
| `.github/workflows/<name>` | The kit's workflow is written beside yours as `kit-<name>`. |
| `LICENSE` and anything else | Yours is kept; the manifest's `license` label follows your LICENSE. Kept files are recorded in `tools/kit-lock.json` as yours, so `make kit-update` never touches them and mentions one only when the kit's version of it changes. |

Template-only material is pruned exactly as `make init` prunes it: links to
it point at the template source and doc bindings to it are dropped. Your
existing `docs/*.md` get an `<!-- index: -->` line from their title (edit
the wording). Afterwards `make check` lists your code as unregistered surfaces:
declare each one in `project.toml` (or list support folders such as tests in
`[repository].infrastructure_paths`), then follow `make next`. A document's
`make <target>` references resolve to the nearest Makefile above it, so
subprojects keep their own targets.

## Adaptation loop

1. Read `VISION.md`, `docs/STACK-DECISION.md`, and the active surfaces.
   Name the accountable owner at init (`make init ... OWNER=<handle>`) or in
   `project.toml` `owners`; the `project-owner` placeholder fails `make check`.
2. If `make init` created `template-bootstrap`, replace it with the first real
   surface before treating verification as product evidence.
3. Run `make inventory` and classify each candidate as product, infrastructure,
   generated output, or unresolved.
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

## Optional capability packs

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

A pack is activated by adding its project-specific surface, commands, and
records to `project.toml` and the documentation index. The kernel does not
generate framework folders or install a skill before a trigger exists.
