---
name: parity-check
description: >-
  Measures how close this build is to the reference product: a feature parity
  score from the feature matrix (weighted by must, should, could) with the
  missing list in build order, plus a screenshot layout diff that ignores
  colour so a rebrand does not count against you. Two standard-library Python
  tools. Use when the user says "how close are we", "what's missing",
  "parity", "is it ready", or "diff the screens".
---

# parity-check

Reads `docs/product/features.csv` (the one matrix, shared with kickoff, recon,
review-mining and `make next`), plus the two screenshot sets. Writes
`reference/parity.md`.

Two tools in this folder, both standard-library Python, no installs
(commands run from the project root):

```bash
python3 .agents/skills/parity-check/parity.py docs/product/features.csv                         # feature parity + missing list
python3 .agents/skills/parity-check/imgdiff.py reference/screens/S07.png reference/build-screens/S07.png --out reference/diffs/S07.png
python3 .agents/skills/parity-check/imgdiff.py a.png b.png --json > reference/diffs/S07.json # for parity.py --visual
python3 .agents/skills/parity-check/parity.py docs/product/features.csv --visual reference/diffs/*.json --markdown > reference/parity.md
```

## What parity means here

**Parity means it does the same job, not that it looks the same.** The
feature score is the number that matters: can a user do everything they could
do in the reference product. The layout score checks structure (is the
information in the same places, in the same hierarchy), because that is what
makes a switcher feel at home. It deliberately ignores colour, because
brand-sweep changes every colour on purpose. Do not chase pixel parity with
the reference product. Its exact look is its trade dress, and it changes
before launch.

## Step 1: feature parity

Make sure `docs/product/features.csv` is current: every row's `status` is
`yes`, `partial` (with a note), `no`, or `skip` (with a reason). `status` is
does this build have it. An old `reference/features.csv` with a `clone`
column still scores (deprecated; rename it to `status`). Then:

```bash
python3 .agents/skills/parity-check/parity.py docs/product/features.csv
```

It weights must 3, should 2, could 1, counts partial as half, leaves out
`skip` rows and rows you added that the reference product does not have
(`source` review-mining, or `original` no), and
prints: the score, must-haves done of total, each area weakest first, and the
missing list in build order. Must-haves not done means not shippable, and it
says so.

## Step 2: layout diff

For each key screen, take two screenshots at the **same viewport** (1440x900
desktop, 390x844 mobile) in the **same state** (same data shape, same tab
open, logged in the same way). The reference product's come from public pages
or the user's own account, saved in `reference/screens/`. This build's go in
`reference/build-screens/`.

```bash
python3 .agents/skills/parity-check/imgdiff.py reference/screens/S07.png reference/build-screens/S07.png --out reference/diffs/S07.png
```

Layout mode (default) turns both into edge maps, cuts them into a grid, and
compares where things are, scoring only cells with something in them. It
reports the score (matches 90+, close 75+, partly 50+, different), the
regions that differ (in the reference screenshot's pixel coordinates, biggest
first), and a height difference if this build's page is much longer or
shorter. Retina and non-retina screenshots compare fine: both are scaled to
the same width.

`--mode pixel` is exact comparison. Use it for your own regressions (this
build today against this build last week), not against the reference.
`parity.py --visual` averages layout scores only and lists pixel-mode or blank
comparisons as ignored.

## Step 3: behaviour diff

Walk each flow in both products and compare what the scores cannot see: clicks
to finish the core flow, what happens on errors, what is remembered between
visits, what emails arrive. Fewer clicks than the reference is a win. Write
each difference as: flow, reference does, build does, fix or keep.

## Step 4: the report

`reference/parity.md`: overall score, feature score, layout score per screen,
missing features in build order, behaviour differences, and a verdict:

- **not shippable**: any must-have missing, or any open blocker issue
- **shippable**: all must-haves done, feature score 80+, no open blocker or
  high-severity issue
- **better than the reference**: shippable, plus fixes from review-mining.
  This is the goal. A straight copy has no reason to exist.

Give honest numbers. A build at 62% is at 62%.

## Output

`reference/parity.md`, the diff images in `reference/diffs/`, and the top five
things to build next. Then the project's issue-backed build loop (AGENTS.md)
for the gaps, or review-mining when parity is there.

## Source

Adapted from the upstream skill in https://github.com/Jakeschincariol/replica-skill (MIT, © 2026 Jake Schincariol); revision: see `project.toml` `[[skills]]`.
