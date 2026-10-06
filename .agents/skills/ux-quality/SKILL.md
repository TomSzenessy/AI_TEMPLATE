---
name: ux-quality
description: "The UI/UX bar for building and reviewing interfaces: platform conventions (Apple HIG, Material), design tokens, every screen state, accessibility, ethical onboarding and persuasion, and screenshot review at real device sizes. Use whenever a change touches what users see or tap."
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

1. Run the real build and screenshot it at 375x812, 768x1024, and 1440x900,
   in light and dark mode when both exist (browser tool or Playwright MCP;
   simulator or emulator for native). If `make capabilities` shows no browser,
   say so and ask the owner for screenshots; never claim a visual review you
   did not do.
2. The reviewer compares the screenshots with this list, `docs/design.md`, and
   the approved mockup, and reports each issue with the screenshot and region.
3. Fix, re-screenshot, and use `parity-check`'s image diff to catch unintended
   layout changes.
4. For key flows, walk through as a first-time user: count steps and time to
   the first moment of value.

## Done when

You ran the real build and looked at it, every state exists, contrast and
accessibility checks pass, screenshots were reviewed with no blocker, and
deviations are recorded in `docs/design.md`.
