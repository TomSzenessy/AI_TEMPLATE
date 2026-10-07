---
name: brand-sweep
description: >-
  Names and rebrands the build so it is the user's own: name candidates with
  the trademark, domain, store and handle checks to run, a new palette checked
  for contrast, a logo brief, a voice guide, and a sweep tool that finds
  anything of the reference product left in the codebase. Use when the user
  says "name my app", "rebrand", "anything of X left", "trademark checks", or
  "before launch".
---

# brand-sweep

Nothing launches under the reference product's identity. This skill is the
line between a copy and your own product.

Reads the angle from `reference/fixes.md` (review-mining) and the token roles
in `reference/design/tokens.json` (design-tokens). Tool in this folder (commands run from the project root):

```bash
python3 .agents/skills/brand-sweep/sweep.py . --avoid "Original Name,Its Company" --domains original.com --colors "#006bff"
python3 .agents/skills/brand-sweep/sweep.py . --config reference/brand.json        # same, from the brand file
```

The sweep only reads. You (the agent) write `reference/brand.md` and
`reference/brand.json` (`avoid`, `domains`, `colors`, optional `exclude`),
which `sweep.py --config` then reads. Colours are hex (`#006bff`, `006bff`,
`#06f`, `#006bffaa`; alpha is ignored); `rgb(...)` or a typo exits 2, never a
silent "Clean".

## Step 1: the name

Read the angle from `reference/fixes.md`. Generate 20 candidates across
styles: descriptive (Booklink), compound (Slotwise), invented (Calvo),
metaphor (Harbor), verb (Book). Then cut to 5 with these filters:

- **Not confusingly similar to the reference product** in sound, look or
  meaning, and not to any other app in the same category. That is the test
  trademark offices use, so it is the test here. No puns on their name, no
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

A new palette, written into the same token roles design-tokens set up. Pick a
primary brand hue from a different family than the reference product's (if
theirs is blue, yours is not a nearby blue). Then:

```bash
python3 .agents/skills/design-tokens/contrast.py reference/design/tokens.json
```

Zero AA failures. Add the reference product's brand colours to
`reference/brand.json` so the sweep catches any that survive.

## Step 4: logo brief

Not a logo, a brief for whoever makes it (the user, a designer, an image
model):

- the idea in one line, tied to the name and angle
- mark type: wordmark, symbol plus wordmark, or monogram
- must work at 16px (favicon) and as a 1024px app icon
- deliverables: SVG, app icon 1024x1024 with no transparency for iOS,
  favicon set, social image 1200x630
- **must not resemble the reference product's mark**: no shared shape, colour
  pair or letterform trick. Put their mark next to the drafts and check.

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

## Output

`reference/brand.md` (name with checks, palette, logo brief, voice),
`reference/brand.json`, updated tokens, rewritten strings, and a clean sweep.
That clean sweep is the pre-launch gate: nothing ships while it exits 1.
Remember: `reference/` must be registered in `project.toml` (see
product-recon).

## Source

Adapted from the upstream skill in https://github.com/Jakeschincariol/replica-skill (MIT, © 2026 Jake Schincariol), revision 77c9436fb3d18c3d58169efb8caf4fe906b0dc51.
