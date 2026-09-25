# Start here

This is the shortest safe route from a fresh checkout to a verified change. It
works for code, games, visual assets, video, data, and documents; only the
quality oracle changes.

## First session

1. Check for root `HANDOVER.md` and read it if present; compare it with the
   working tree. **Done when** the current goal, branch, and next action are
   known without relying on chat history.
2. Read [`../AGENTS.md`](../AGENTS.md), [`../project.toml`](../project.toml), and
   this [documentation index](./README.md). For a new project, read
   [`../VISION.md`](../VISION.md), [`STACK-DECISION.md`](./STACK-DECISION.md),
   and [`ADAPTATION.md`](./ADAPTATION.md). **Done when** you can name the
   project purpose, active surfaces, owners, and verification commands without
   guessing.
3. Run `make inventory` and `make check`. **Done when** every product directory
   is either declared in `project.toml` or consciously left as infrastructure.
4. Run the smallest declared check for the surface you will touch. **Done when**
   the command and its observable result are recorded in the issue or handoff.
5. If the project is not initialized, run `make init NAME=my-project KIND=...`
   and then replace the license/owner/launch placeholders deliberately. **Done
   when** `make doctor` reports only intentional gates.
6. Replace the `template-bootstrap` surface declared by `make init` with the
   first real product surface, following [`ADAPTATION.md`](./ADAPTATION.md).
   **Done when** the manifest names a real owner, oracle, and verification path.

## Profiles and issue route

Read `[governance].profile` in `project.toml` before filing work:

- `agent-first` uses a compact issue contract and can review a local
  `Local-WAL: <id>` draft before a GitHub issue exists. `Local-WAL` is only a
  pre-filing draft; the configured GitHub issue register remains the durable
  task/status record. Once filed, use the issue number and a real
  commit/diff/artifact in the review packet.
- `regulated` requires the full canonical headings, public disclosure review,
  and `REVIEW_EVIDENCE`; active security findings stay private.
- `minimal` delegates issue/review tooling to the host organization; the local
  `repoctl issue`/`labels` commands intentionally decline to file or synchronize
  it. It still keeps manifest/path/verification checks here.

If the task needs a missing specialist capability, read
[`resources.md`](./resources.md) and [`skills.md`](./skills.md), discover only
the capability that matches the trigger, and record its reviewed provenance
before using it. Retain verified capabilities while they remain trusted and
useful. Do not load or install every available skill.

Do not switch profiles to bypass a blocker. Record the decision and its reason
in the issue.

## Every task

- Start or update the issue-backed write-ahead record.
- Read the nearest scoped instructions and the trigger document from the index.
- Reproduce a failure before changing it.
- Make the smallest coherent change at the correct seam.
- Run focused verification, `make verify`, and the real-artifact check.
- Ask a fresh critic to review the result with `make review-packet`.
- Reconcile issue, manifest, docs, and residual risks in the same change.

## Non-code surfaces

Use the same loop with a domain-specific oracle:

- **Website/app:** browser interaction, responsive screenshots, accessibility
  checks, and a real request/response path.
- **Game:** deterministic scenario, performance trace, saved-state check, and a
  rendered play session.
- **Blender/3D:** reproducible render, contact sheet or turntable, geometry and
  material sanity checks, and visual comparison at the target resolution.
- **Video/audio:** source-to-export render, codec/container validation, waveform
  or frame inspection, and a short representative playback.
- **Backend/data:** request/response and state assertions, migration/retention
  evidence, failure/retry behavior, and real persistence inspection.
- **Document/legal:** source citations, link checks, jurisdiction/counsel gate,
  and a human-readable rendered review.

A command that exits zero is not a quality oracle until it proves the intended
artifact or behavior. For a real deployment or release, follow
[`production.md`](./production.md) and attach its evidence rows.
