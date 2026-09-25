# Project adaptation

The template is a small kernel plus capability packs, not a universal
application scaffold. The kernel stays responsible for navigation, the project
manifest, issue-backed intent, path safety, declared verification, and bounded
review. Project-specific policy and code are added only after the vision intake
identifies a real need.

## Adaptation loop

1. Read `VISION.md`, `docs/STACK-DECISION.md`, and the active surfaces.
2. Run `make inventory` and classify each candidate as product, infrastructure,
   generated output, or unresolved.
3. Ask the owner only for choices that change product direction, data/security
   boundaries, deployment, cost, or an irreversible dependency.
4. Record the decision and acceptance evidence in the issue/WAL.
5. Add only the smallest surface, toolchain, and verification needed for the
   first real artifact. A single-file product may declare `kind = "file"`,
   `"script"`, `"document"`, or `"asset"` and point at the file; directory
   surfaces remain the default.
6. Re-run inventory and the declared checks; remove or deprecate anything with
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
