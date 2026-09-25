# Verification and independent quality loop

“Done” means the issue's acceptance criteria have observable evidence. A build,
lint run, or green return code is necessary but not sufficient.

## Profile-aware evidence

`agent-first` requires a critic for commandless/creative surfaces but lets the
host own ordinary issue/review ceremony; `regulated` requires the full
disclosure/body record; `minimal` delegates the critic to the host. A local
pre-filing packet uses `Local-WAL: <id>` and a real commit/diff/artifact. It is
not a replacement for the GitHub issue register. See `project.toml` and
`AGENTS.md` for the current profile.


Use the smallest sufficient evidence, then escalate:

1. **Static:** parse/type/lint/schema checks.
2. **Focused behavior:** unit or contract test at the changed seam.
3. **Integration:** real database, filesystem, renderer, browser, queue, or
   provider adapter with a failure/retry path.
4. **Artifact:** inspect the rendered UI, image, frame, audio waveform, export,
   API payload, row/file/object state, or performance trace users receive.
5. **Independent review:** a fresh agent or reviewer checks the issue, diff,
   standards, security/privacy impact, and artifact without editing first.
6. **Deployment/provider/hardware/counsel evidence:** attach separately; local
   evidence never silently substitutes for it.

## The quality loop

For a substantial or subjective deliverable:

1. Split the issue into independently verifiable deliverables.
2. Give each deliverable a builder brief with its oracle and constraints.
3. Run builders in parallel only when their seams do not conflict.
4. Give a fresh, demanding critic the original acceptance criteria and the real
   artifact. The critic should try to falsify the claim, not rationalize it.
5. Fix confirmed blockers, rerun the oracle, and record the new evidence.
6. Stop after three focused iterations or when the marginal change no longer
   improves the declared bar. File the remaining disagreement as an issue.

This generalizes the useful part of the Matt Shumer “fan out and critic” loop:
independent coverage, harsh review, observable comparison, and iteration. It
does **not** accept an unbounded “perfect” promise. Quality is relative to a
declared target, resolution, accessibility level, frame rate, privacy boundary,
or other measurable oracle.

## Domain oracles

- **Web/app:** functional browser path, responsive screenshots, accessibility,
  performance budget, and no console/network errors on the critical path.
- **Game:** deterministic gameplay scenario, input/frame/performance trace,
  save/load check, and rendered play session at target settings.
- **3D/Blender:** deterministic scene/render command, geometry/material sanity,
  contact sheet or turntable, and visual comparison at delivery resolution.
- **Video/audio:** source-to-export render, codec/container and duration checks,
  representative playback, and waveform/frame inspection.
- **Backend/data:** real request and persisted state, authorization negatives,
  retry/idempotency, migration/retention behavior, and failure evidence.
- **Legal/privacy:** factual source inventory, link/format validation, counsel
  gate where applicable, and a rendered human review.

## Before completion

Run `make verify`, inspect the real artifact, generate a fresh review packet with
`make review-packet ISSUE_FILE=...`, and resolve every blocker. Report skipped
checks and external gates explicitly. “No issues found” means the declared scope
was checked to the stated coverage—not that the entire universe is bug-free.
