---
name: design-tokens
description: >-
  Builds design tokens — colour roles, type scale, spacing, radius, shadows
  and every component with its states — for a reference product you studied
  or for your own original product, with original assets instead of logos,
  icons, illustrations or licensed fonts. Includes a WCAG contrast checker.
  Use when the user says "design tokens", "match the design system", "WCAG
  contrast", or "make it look like X".
---

# design-tokens

Two modes. **Reference mode** (matching a product you studied): reads
`reference/recon.md` and the screenshots in `reference/screens/`, both from
product-recon. **Original mode** (your own product, no reference): reads the
confirmed goal, users and accepted design from `VISION.md` and
`docs/design.md` (product-kickoff writes both) and skips only the reference
comparisons, marking them not applicable. Both modes write `tokens.json`
(template: tokens.json in this folder), `tokens.css`, the theme mapping, and
`components.md` — reference mode under `reference/design/`, original mode
under `docs/design/`. Original mode never invents a competitor: if the brief
is missing, ask the owner the few blocking questions rather than fabricate
one.

```bash
# reference mode
python3 .agents/skills/design-tokens/contrast.py reference/design/tokens.json
# original mode
python3 .agents/skills/design-tokens/contrast.py docs/design/tokens.json
```

## The rules

What you rebuild is the **system**: the roles, the scale, the patterns, the
way a form or a modal behaves. Those functional patterns are widespread and
users expect them; they are not owned by any one product, though a specific
expression of them can be.
What you never take:

- **Logos, icons, illustrations, photos, sounds.** Use an open icon set
  (Lucide, Phosphor, Heroicons, Tabler, all MIT or similar) and make or
  commission your own illustrations. Do not trace theirs.
- **Licensed fonts.** If the reference product uses a paid or proprietary
  font, pick an open one with the same job: Inter, Geist, IBM Plex, Manrope,
  Source Serif.
- **Their copy.** Every label and empty state gets written fresh.
- **Their brand colour.** Record it as a role (`accent`), use a neutral
  placeholder now, and brand-sweep gives you your own. A signature colour
  plus a distinctive layout may be protected as trade dress in some
  jurisdictions; change both before launch and get legal advice if you are
  unsure.

## Step 1: measure, do not guess

Reference mode — from the screenshots (zoom in, use a colour picker on the
user's machine). Original mode — from the confirmed design brief
(`docs/design.md`): the chosen direction, mood words and any colours the owner
already picked. When the brief is silent, use the defaults below.

- **Colour roles**, not colours: bg, surface, border, border-input, text,
  text-muted, accent, on-accent, danger, success, warning. Count how many
  greys the app really uses. Usually 5 to 7.
- **Type scale**: sizes, line heights, weights. Snap to a scale (12, 14, 16,
  20, 28, 40 is common). Note the font category, not the font file.
- **Spacing**: measure gaps between elements. It is almost always a 4 or 8
  base. Write the scale.
- **Radius, shadow, motion**: two or three of each.
- **Layout**: max content width, grid, breakpoints, sidebar width, header
  height.

## Step 2: write the tokens

Fill the mode's `tokens.json` (`reference/design/` or `docs/design/`). Keep the
role names. brand-sweep only changes values. Generate the mode's
`tokens.css` as custom properties
and map them into the project's theme (Tailwind's theme where that is the
stack) so components use `bg-surface text-muted`, never raw hex.

Add a `pairs` list for every text and background combination the app uses
(including `["focus", "bg", "ui"]` for the focus ring), then:

```bash
python3 .agents/skills/design-tokens/contrast.py reference/design/tokens.json   # or docs/design/
```

AA is the floor (the checker owns the thresholds). Hex may be bare or `#`,
3, 4, 6 or 8 digits (alpha ignored: composite a transparent pair against the
actual resolved background before the opaque check). It exits 1 on a failure;
zero failures is a checked floor, not WCAG certification. Fix it in the tokens,
not per component.

## Step 3: component specs

For every component in product-recon's list (reference mode) or in the
accepted design brief (original mode), one block in the mode's
`components.md`:

```
Button
  variants  primary, secondary, ghost, danger
  sizes     sm 32px, md 40px, lg 48px
  states    default, hover, active, focus-visible (2px ring, accent), disabled, loading
  tokens    bg accent, text on-accent, radius md, font sm/600
  a11y      real <button>, visible focus, loading keeps the label for screen readers
  used on   S02, S07, S09
```

Every state the reference recon saw or the confirmed original brief requires,
plus the ones it should have: focus, disabled, loading, error, empty.
Keyboard and screen reader behaviour is part of the spec.

## Step 4: build the primitives

Build the components in code once, in isolation (a `/design` route or
Storybook), before any screen. Use an accessible base if the stack has one
(Radix, shadcn/ui, React Aria). Screenshot the page. That is the design
system check.

## Output

`tokens.json`, `tokens.css`, the theme mapping, `components.md`, the
primitives built, and a contrast report with zero AA failures. Then the
project's issue-backed build loop (AGENTS.md) builds screens against the
primitives.
