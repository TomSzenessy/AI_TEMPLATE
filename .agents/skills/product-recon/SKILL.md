---
name: product-recon
description: >-
  Reverse-engineer a reference product into a recon map: screens, flows,
  components, inferred data model, feature matrix — from public pages,
  screenshots, listings, help docs and the user's own account. Use when the
  user says "clone this app", "reverse engineer X", "map out this product",
  "how does X work", "build our own version of X", or "competitive analysis".
---

# product-recon

Everything downstream — the design tokens, the build, the parity check —
builds from what this writes. A bad recon map means a bad build.

```
reference/recon.md        the recon map (template: recon-map.md in this folder)
reference/screens/        reference product's screenshots. Never shipped.
docs/product/features.csv the feature matrix, shared with product-kickoff,
                          review-mining, parity-check and `make next`
```

`reference/` holds recon evidence only (screens, notes, the map); the matrix
lives in `docs/product/features.csv` so `make next` sees it.

Once per project, add `"reference"` to `infrastructure_paths` in `project.toml`
(or declare it a surface): `make check` flags unregistered top-level dirs. The
other product skills write under `reference/` too and rely on this step.

## The rules, before anything else

This skill studies **functionality and UX patterns**, clean-room style: what
the product does and how a user moves through it, taking nothing it owns.

- **Public sources and the user's own account only.** Never someone else's
  account, never a password, never past a paywall or a login by any trick.
- **Reading, not scraping.** No crawlers, no bulk downloads, no loops. With a
  browser tool on the user's own browser, read at human speed, user present.
- **No source code, no private APIs.** No decompiling, no reading its
  bundles, no logging network calls to copy endpoints; public API docs are fine.
- **Check the terms.** Some terms forbid using an account to build a competing
  product; under those, say so and work from public sources only.
- **Screenshots are reference.** They live in `reference/screens/`, are used
  to compare layouts, and never go into the build.

## Step 1: scope

Ask three things, or propose answers and get a yes:

1. **Which product, which platform.** Web, iOS, Android, desktop.
2. **Which slice.** "All of Notion" is not a project; "Notion's pages,
   blocks and sharing" is. Default to the core loop: the flow users pay for.
3. **What it is for.** The user's own business, a niche, a competitive
   read, a product to sell.

## Step 2: list the sources

Build a sources table first, a URL on every row, in order of value:

| source | what it gives you |
| --- | --- |
| help center / docs | the most complete feature list there is, and the settings |
| pricing page | which features matter (they gate them) |
| changelog | what was added recently, what the team thinks is important |
| app store listing | screenshots of every key screen, the pitch, ratings |
| public walkthrough videos | real flows, click by click |
| marketing site | positioning, the core loop in their words |
| the user's own account | the real thing, every state, driven by the user |
| public API docs | the data model, almost for free |

## Step 3: screen inventory

One row per screen, in the Screens table of `recon-map.md`. IDs are stable:
S01, S02... Every other file refers to them.

States matter: empty, loading, filled, error, permission denied, mobile. An
empty state you did not record is an empty state you will not build.

## Step 4: user flows

F01, F02... Each one is a goal and the screens it passes through (the Flows
block of `recon-map.md`). Count the happy-path clicks — the number to beat —
and the edge cases: no availability, time zones, the slot taken mid-form.

## Step 5: components

Every repeated UI part: buttons, inputs, date pickers, modals, tables,
toasts, nav. Name, variants, states, which screens use it.

## Step 6: inferred data model

Entities, fields and relationships, each with its evidence (screen IDs,
help articles) and a confidence: high, medium, guess. Mark guesses as
guesses. The build turns this into a real schema.

## Step 7: feature matrix

Append one row per feature the reference product has to
`docs/product/features.csv` (columns: feature, area, priority, status,
evidence, acceptance, source; template: `features.csv` in this folder; create
the file with its header if kickoff has not). Priority is must / should /
could. `status` is does this build have it, starting at `no` and filled in
during the build; `source` is `product-recon`. A must row needs an
acceptance criterion. Quote any value that contains a comma. parity-check
and `make next` both read this file.

## Step 8: what cannot be cloned

List it honestly, as `status=skip` rows with the reason in `acceptance`: licensed content (a music
catalogue, a stock library), the network and its users, data the product
owns, partner deals, hardware, regulated licences (banking, health).
Learning from a product means the features and the flow, not what it owns.

## Step 9: size it

Screens, flows, entities, and the hard parts (realtime, sync, payments,
calendar or email integrations, offline). Give a size: S (a weekend), M (a
few weeks), L (a quarter), XL (rescope it). No promises of a perfect clone.

## Output

`reference/recon.md` and the new rows in `docs/product/features.csv`, then a five-line summary:
the core loop, screen and flow counts, the three hardest parts, what is out
of scope, and the next step: design-tokens, then the project's issue-backed
build loop (AGENTS.md).

## Source

Adapted from the upstream skill in https://github.com/Jakeschincariol/replica-skill (MIT, © 2026 Jake Schincariol); revision: see `project.toml` `[[skills]]`.
