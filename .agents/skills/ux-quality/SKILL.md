---
name: ux-quality
description: "The UI/UX bar for building and reviewing interfaces: platform conventions (Apple HIG, Material), design tokens, every screen state, accessibility, ethical onboarding and persuasion, and screenshot review at real device sizes. Use whenever a change touches what users see or tap."
pack: product
---

# UX quality

The bar for anything users see or touch. Builders apply it while working; the
`critic` role reviews against the same list. Project-specific choices live in
`docs/design.md` (created by `product-kickoff`) and override nothing here
silently: record deliberate deviations there.

## Foundations

- **Platform conventions first:** Apple Human Interface Guidelines on iOS and
  macOS, Material 3 on Android, established web patterns on the web. Deviate
  deliberately and record why.
- **Tokens are the single source:** colours, type, spacing, radius, and motion
  come from one tokens file (the `design-tokens` skill defines its format),
  never ad-hoc values. Check contrast with
  `python3 .agents/skills/design-tokens/contrast.py <tokens file>`.
- **Hierarchy:** one primary action per screen, a consistent spacing scale,
  readable body text (16 px on the web, Dynamic Type on Apple platforms).

## Visual bar: designed, not assembled

- **Build on proven parts:** a component library and one icon set that fit the
  stack (for example shadcn/ui or Radix with Lucide on the web; native controls
  and SF Symbols or Material Symbols on mobile), styled by the tokens.
- **Rhythm:** a 4 or 8 point spacing scale, three or four type sizes with a
  clear hierarchy, one accent colour used sparingly, consistent radius and
  elevation.
- **Real content:** real copy, names, and data shapes; never lorem ipsum or
  framework defaults (favicon, titles, starter pages).
- **Life:** subtle motion (150-250 ms) on state changes, immediate feedback on
  every tap, empty states with a helpful next action.
- **Benchmark:** put your screenshots next to the design references in
  `docs/product/research.md`. If yours would look out of place among them,
  iterate before moving on.

## Avoid the generic AI look

Defaults a model reaches for when the brief leaves the look free; each needs a
reason from the product, not habit. A recorded brief in `docs/design.md` wins.

- **Palette:** purple/indigo gradients; near-black with one neon accent and
  glowing edges; warm cream ground with serif display and a terracotta
  accent. If the look can be guessed from the category alone, redo it. Pick
  light or dark from where and when it is used, not the category.
- **Type:** one overused display face (Inter as display, Space Grotesk,
  Fraunces, Playfair, DM Sans), gradient text, a kicker/eyebrow above every
  heading, mono type as a "technical" costume, 01/02/03 section numbers.
- **Layout:** rows of same-size icon + heading + text cards, nested cards,
  the big-number hero-metric block, a modal for a task that needs no
  interruption, oversized padding everywhere.
- **Surface:** decorative glass/blur, coloured `border-left` accents on cards
  and alerts, hard offset shadows outside a deliberately neobrutalist world,
  maximum rounding on everything, sparkline/ring filler instead of content.
- **Icons:** emoji or unicode glyphs as icons; mix of stroke weights.
- **Unthemed defaults:** browser text selection, caret, scrollbars, focus
  rings, and untabulated numerals in data tables; style them from the tokens.
- **Motion:** the same entrance animation on every section; one authored
  moment beats scattered effects.

## Every screen has every state

Empty, loading (skeletons over spinners), error (what happened and how to
recover), offline, partial data, success, long or localized content, and
permission denied. A screen with only the happy path is not done.

## Accessibility is part of done

WCAG 2.2 AA contrast; touch targets of at least 44 pt (iOS) or 48 dp
(Android); screen-reader labels; logical focus and keyboard order; respect
reduced motion; layouts survive 200% text size; never use colour alone.

## Onboarding and user psychology, used ethically

- **Time to value:** let people do the core thing before sign-up when
  possible; ask for permissions in context, with the reason.
- **Lower effort:** progressive disclosure, good defaults, few fields,
  recognition over recall, visible progress.
- **Feedback:** respond within about 100 ms; optimistic updates where safe;
  prefer undo over confirmation dialogs.
- **Never deceive:** no dark patterns (confirmshaming, hidden costs, forced
  continuity, pre-checked consent, fake urgency or social proof). Privacy and
  cancel choices get equal visual weight.

## Copy

Plain and specific; buttons start with a verb; errors say what happened and
what to do next; no blame, no jargon.

## Review loop (vision-capable reviewer)

Vocabulary: **audit** is measurable (contrast, states, targets, responsive,
performance via `web-quality`) and fixes nothing; **critique** is judgment
(hierarchy, fit to the product, specificity, cognitive load: more than four
visible choices at a decision point is a finding; run it with the `critic`
role, not the builder); **polish** fixes what both found, in this order:
blocked or inaccessible tasks, missing states, system drift, visual detail.
Steps 1-2 below are audit and critique, step 3 is polish.


1. Run `make ui-review` (mechanics in `docs/building.md`). For native apps
   use the simulator or emulator. Without a browser, say so and ask the owner for
   screenshots; never claim a visual review you did not do.
2. Open every screenshot (you or the `critic` role, vision-capable) and compare
   it with this list, `docs/design.md`, the approved mockup, and the design
   references. In the run's entry in `docs/product/ui-reviews.md`, write
   findings and set `Verdict: pass` only when nothing blocks. A passing review
   of the current code closes a UI feature and is required before release.
3. Fix, re-screenshot, and use `parity-check`'s `imgdiff.py --mode pixel` at the
   same viewport and state to catch unintended changes (layout mode ignores
   colour and text).
4. For key flows, walk through as a first-time user: count steps and time to
   the first moment of value.

Optional external catalogs (not installed; vet with `skill-scout` first):
[UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
(searchable styles, palettes, font pairings) and
[Impeccable](https://github.com/pbakaus/impeccable) (design commands with an
anti-pattern detector).

## Done when

You ran the real build and looked at it, every state exists, contrast and
accessibility checks pass, screenshots were reviewed with no blocker, and
deviations are recorded in `docs/design.md`.

Upstream depth: `make upstream ID=impeccable-frontend-polish` lists pinned files (e.g. typography → typeset.md); fetch only the one your step needs.
