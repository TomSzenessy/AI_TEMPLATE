# Project adaptation

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
| `VISION.md` | Keep as the current product-direction record. | Never remove; revise it when the product direction changes. |
| `docs/STACK-DECISION.md` | Keep the accepted decision and its rationale. | Replace a superseded decision with a new record or explicit revision. |
| `project.toml` example comments | Useful while adapting. | Remove unused examples/comments once the real manifest is understood. |
| `[[surfaces]] id = "template-bootstrap"` | Created by `make init` as a visible pending declaration, not a product check. | Replace it with the first real surface; never treat its governance check as product evidence. |
| `HANDOVER.template.md` | Keep the reusable local/committed templates. | Delete ignored `HANDOVER.md` after a session; keep a committed handoff only while another actor needs it. |
| `docs/ISSUE_TEMPLATE.md` and `.github/ISSUE_TEMPLATE/` | Keep as `agent-first` intake schemas. | Do not turn them into a status board; remove/disable native forms in `regulated` or `minimal` profiles. |
| `docs/legal/*.template.md` | Keep while a document may apply. | Replace with a reviewed final document and update `legal_document_paths`; unused templates may be removed from a project copy. |
| `docs/research/` | Keep as provenance while its guidance matters. | Archive/remove after the knowledge has been internalized and no decision cites it. |
| `docs/ERROR_LOG.md` | Keep as an append-only solved-failure ledger. | Do not use it for open work; link open work to Issues. |
| `.agents/skills/` | Keep the small first-party workflows and verified reusable capabilities. | Retain a reviewed skill while it remains trusted and useful; remove it only with a documented trust, permission, maintenance, or owner decision. |
| `.security/` | Keep and refresh the threat model/config as security surfaces change. | Do not delete security evidence merely to make a check quiet. |

A project should be able to remove unused optional material without removing
its operating contract, history, or evidence.

## Adaptation loop

1. Read `VISION.md`, `docs/STACK-DECISION.md`, and the active surfaces.
2. If `make init` created `template-bootstrap`, replace it with the first real
   surface before treating verification as product evidence.
3. Run `make inventory` and classify each candidate as product, infrastructure,
   generated output, or unresolved.
4. Ask the owner only for choices that change product direction, data/security
   boundaries, deployment, cost, or an irreversible dependency.
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

A pack is activated by adding its project-specific surface, commands, and
records to `project.toml` and the documentation index. The kernel does not
generate framework folders or install a skill before a trigger exists.
