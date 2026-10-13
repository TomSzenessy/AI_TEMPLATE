---
name: brand-sweep
description: >-
  Names and rebrands the build so it is the user's own: name candidates with
  the trademark, domain, store and handle checks to run, a new palette checked
  for contrast, a logo brief, a voice guide, and a sweep tool that finds
  anything of the reference product left in the codebase. Works for a product
  you are matching a reference and for an original product with no reference.
  Use when the user says "name my app", "rebrand", "anything of X left",
  "trademark checks", or "before launch".
---

# brand-sweep

Nothing launches under the reference product's identity. This skill is the
line between a copy and your own product.

Two modes. **Reference mode** reads the angle from `reference/fixes.md`
(review-mining) and the token roles in `reference/design/tokens.json`
(design-tokens). **Original mode** (your own product, no reference) reads the
angle from the confirmed goal and users in `VISION.md` and `docs/design.md`,
and skips only the reference comparisons, marking them not applicable.
Original mode never invents a competitor: if the brief is missing, ask the
owner the few blocking questions rather than fabricate one. Tool in this
folder (commands run from the project root):

```bash
python3 .agents/skills/brand-sweep/sweep.py . --avoid "Original Name,Its Company" --domains original.com --colors "#006bff"
python3 .agents/skills/brand-sweep/sweep.py . --config reference/brand.json        # same, from the brand file
```

The sweep only reads. You (the agent) write `brand.md` and `brand.json`
(`avoid`, `domains`, `colors`, optional `exclude`) under `reference/` in
reference mode or `docs/design/` in original mode, which `sweep.py --config`
then reads. Colours are hex (`#006bff`, `006bff`, `#06f`, `#006bffaa`; alpha is
ignored); `rgb(...)` or a typo exits 2, never a silent "Clean".

## Step 1: the name

Reference mode reads the angle from `reference/fixes.md`; original mode reads
it from `VISION.md` and `docs/design.md`. Generate 20 candidates across
styles: descriptive (Booklink), compound (Slotwise), invented (Calvo),
metaphor (Harbor), verb (Book). Then cut to 5 with these filters:

- **Not confusingly similar to the reference product** in sound, look or
  meaning, and not to any other app in the same category. Trademark offices
  consider confusion when assessing similarity; use that as a screening test,
  not as legal clearance (see Step 2). No puns on their name, no
  "-ly" twin.
- Short, spellable after hearing it once, no awkward meaning in big languages.
- Says something about the angle, or at least does not fight it.

## Step 2: the checks, run, not assumed

For each of the 5, a row per check. Mark each **to run**, or the result with
the date it was run. Never write "available" for a check nobody ran.

| check | where |
| --- | --- |
| US trademark | tmsearch.uspto.gov, the app's class (usually 9 and 42) |
| EU trademark | euipo.europa.eu eSearch, or TMview for many offices |
| Canada | ised-isde.canada.ca trademarks database |
| global | WIPO Global Brand Database |
| domain | `whois name.com`, or the registrar's search |
| App Store and Play | search the exact name |
| handles | X, Instagram, TikTok, GitHub |
| the web | search "name + category" |

These are screening checks, not legal clearance. Before spending money on
the name, a trademark lawyer should do a proper search.

## Step 3: palette

A new palette, written into the same token roles design-tokens set up
(`reference/design/` or `docs/design/`). Reference mode: pick a primary brand
hue from a different family than the reference product's (if theirs is blue,
yours is not a nearby blue). Original mode: pick a hue that fits the goal
angle and any colours the owner already chose; there is no reference to
rotate away from. Then:

```bash
python3 .agents/skills/design-tokens/contrast.py reference/design/tokens.json   # or docs/design/
```

Zero failures. Reference mode: add the reference product's brand colours to
`reference/brand.json` so the sweep catches any that survive. Original mode:
if no reference colours exist, record that in `brand.json` and rely on the
manual artifact checks in Step 6.

## Step 4: logo brief

Not a logo, a brief for whoever makes it (the user, a designer, an image
model):

- the idea in one line, tied to the name and angle
- mark type: wordmark, symbol plus wordmark, or monogram
- must work at 16px (favicon) and as a 1024px app icon
- deliverables: SVG, app icon 1024x1024 with no transparency for iOS,
  favicon set, social image 1200x630
- **must not resemble the reference product's mark** (reference mode): no
  shared shape, colour pair or letterform trick. Put their mark next to the
  drafts and check. Original mode: the mark must be your own — no copying of
  any known brand's shape, colour pair or letterform; check against the
  design references in `docs/product/research.md` if any exist.

## Step 5: voice

Three words for how it sounds, with what each does not mean ("direct, not
blunt"). Five do and don't pairs. Then rewrite the 10 most-seen strings in
the build (sign up, empty states, the main button, the confirmation, the
error) in that voice. All fresh, none echoing the reference product's
phrasing.

## Step 6: the sweep

Replace every placeholder name, colour and string. Then:

```bash
python3 .agents/skills/brand-sweep/sweep.py . --config reference/brand.json
```

It searches file contents and file names for the reference product's name
(also inside identifiers like `CalendlyEmbed`), domains and colours, skipping
`node_modules`, build output and the top-level `reference/`, `.agent/` and
`.review/` folders (where their name belongs). Pass `--include-reference` to
check `reference/` too, for example if it sits inside `public/`.

product-kickoff requires naming the reference product in `docs/product/research.md`
and `docs/design.md`; those are scanned, so exclude them (repeatable
`--exclude <glob>`, or `"exclude": [...]` in `brand.json`):

```bash
python3 .agents/skills/brand-sweep/sweep.py . --config reference/brand.json \
  --exclude docs/product/research.md --exclude docs/design.md
```

Exclude only research and planning docs, never shipped code or copy.
Exit 1 means something is left; exit 2 means bad input.
Fix until it says clean. Also check by eye: the favicon, the page titles, the
email templates, the OG image, the app icon.

**Original mode with no reference product:** there is no reference name,
domain or colour to sweep. Do not fabricate avoid-terms to force a clean CLI
exit, and do not claim the sweep passed. Record in `brand.md` that no
reference identity exists (not applicable), skip the `sweep.py` invocation,
and run the manual artifact checks above by eye instead. The exit 1/2 gate
is unchanged: it still blocks on leftover reference material when a reference
does exist.

## Output

`brand.md` (name with checks, palette, logo brief, voice) and `brand.json`
under `reference/` (reference mode) or `docs/design/` (original mode),
updated tokens, rewritten strings, and a clean sweep (reference mode) or the
manual artifact-check record (original mode). That clean sweep is the
pre-launch gate: nothing ships while it exits 1.
