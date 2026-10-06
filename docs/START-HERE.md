# Start here

The shortest safe route from a fresh checkout to a verified change, for code,
games, media, data, and documents alike; only the quality oracle changes.

## First session

1. `make start` (a hooked host does this for you), then `make capabilities`.
   **Done when** you know the branch, the handover state, the open
   self-healing findings, and which tools (browser, search, docs, `gh`) work here.
2. Read [`../AGENTS.md`](../AGENTS.md) and skim the [index](./README.md). For a
   new project, read [`../VISION.md`](../VISION.md),
   [`STACK-DECISION.md`](./STACK-DECISION.md), and [`ADAPTATION.md`](./ADAPTATION.md).
   **Done when** you can name the purpose, surfaces, owners, and checks.
3. Uninitialized copy: `make init NAME=my-project KIND=web`, then replace the
   license, owner, and launch placeholders. **Done when** `make doctor` reports
   only intentional gates.
4. Replace the `template-bootstrap` surface with the first real one and bind
   its explaining doc with `<!-- covers: -->`. **Done when** `make check` is green.

## Every task

`make where` → issue (per `make risk`) → reproduce → smallest change → update
covering docs → `make finish` → `make verify` → critic per tier → reconcile.
Delegate bounded pieces with [`delegation.md`](./delegation.md).

## Quality oracles by surface

- **Website/app:** browser path (Playwright MCP), responsive screenshots, accessibility, no console errors.
- **Game:** deterministic scenario, performance trace, save/load, rendered session.
- **3D/Blender:** reproducible render, contact sheet, geometry and material checks.
- **Video/audio:** source-to-export render, codec/duration checks, frame or waveform inspection.
- **Backend/data:** real request and persisted state, authorization negatives, retries, migrations.
- **Document/legal:** citations, link checks, counsel gate, rendered review.

A command that exits zero is not an oracle until it proves the artifact. For
releases follow [`production.md`](./production.md).
