---
name: product-kickoff
description: "Turns 'build me an app/site/game' into confirmed decisions before any code: asks the owner a short round of questions with recommendations (users, platforms, stack, visual style, onboarding, data), shows two or three mockup directions, and records the choices. Use at the start of every new product or major reshaping."
---

# Product kickoff

Outcome: before any product code, the owner has confirmed who it is for, the
platforms, the stack, and a visual direction they have actually seen; the
decisions are recorded where every later agent finds them.

## 1. Understand before asking

- Restate the idea in one sentence and name the riskiest assumption.
- If the owner names a reference product, run `product-recon` (and
  `review-mining` for what its users hate); delegate market or reference
  research to the `researcher` role. Bring findings into the questions.

## 2. Ask one round of questions

Ask everything in one message (use the host's question tool when it has one).
Give each question options and your recommendation, so "go with your picks"
is a valid answer. Ask only what changes direction:

1. **Users and goal:** who, which problem, what success looks like (one metric).
2. **Platforms:** web, iOS, Android, desktop; offline needed?
3. **Stack:** recommend from platforms, team skills, and constraints.
   Defaults to start from (verify current versions with Context7 or the
   `researcher` role before scaffolding; never choose by popularity alone):

   | Need | Default | Consider instead |
   |---|---|---|
   | Web app | React + Next.js + Tailwind (+ shadcn/ui) | SvelteKit; Astro for content sites |
   | iOS + Android, one codebase | Expo (React Native) | Flutter for highly custom, pixel-identical UI |
   | Best native feel, one platform | SwiftUI / Jetpack Compose | — |
   | Game | Godot or Unity by scope; web canvas for small games | — |
   | Backend | Managed (e.g., Supabase) until scale or control demands own services | — |

4. **Visual style:** platform-native (Apple HIG, Material 3) or a custom brand;
   two or three apps or sites they like and why; mood words; light, dark, or
   both; existing logo or colours.
5. **First-run and core flow:** what a new user does in the first minute;
   is sign-up needed before value?
6. **Data, accounts, payments, privacy:** personal data means `docs/privacy.md`.
7. **Constraints:** budget, deadline, hosting, must-use services, languages.

Ask a second round only if an answer opens a new high-impact choice. Never
assume answers: if you cannot ask (headless run, tool unavailable) or the owner
has not answered, print the questions with your recommendations and stop. Only
an explicit "use your picks" counts as approval.

## 3. Show mockups before building

- Produce two or three clearly different directions for the one or two most
  important screens (usually first-run and the main screen), with the same
  content so only the design differs. Static HTML + Tailwind renders anywhere;
  use platform previews when the stack is native.
- Render them at phone and desktop sizes with the browser tool (Playwright
  MCP), check them against `ux-quality` yourself, then show the screenshots to
  the owner with a one-line rationale per direction.
- Iterate on the chosen direction once or twice. Keep mockups in ignored
  `.agent/mockups/` unless the owner wants them in the repository.

## 4. Plan the delivery

- **Architecture sketch:** data model, main API or screen contracts, auth,
  hosting, and how it grows (the "Built to scale" section of
  `docs/engineering.md`). Record hard-to-reverse choices as ADRs.
- **Walking skeleton first:** the thinnest end-to-end path (one screen, one
  request, one stored record), deployed early.
- **Vertical slices:** split the MVP into user-visible slices, each shippable
  and verifiable on its own; one issue per slice under an epic issue, ordered by
  risk and value. No Markdown roadmap.
- **Success metric:** how the metric from question 1 will be measured after
  launch, with privacy-respecting analytics only where it is needed.

## 5. Record and hand off

- `VISION.md` (status accepted), `docs/STACK-DECISION.md` (decision, rejected
  alternatives, and why).
- `make new KIND=doc NAME=design GROUP=design DESC="Visual direction, tokens, and UX principles; before any UI work"`,
  then fill it with the chosen direction, references, and tokens (the
  `design-tokens` conventions and contrast checker apply).
- File the epic and slice issues, then run the `stack-foundation` skill for
  the walking skeleton; its surface's quality oracle includes the `ux-quality`
  review. Finish with `make done`.

## Done when

- The owner explicitly confirmed platforms, stack, and one mockup direction.
- An epic with ordered slice issues exists, starting with the walking skeleton.
- `VISION.md`, `docs/STACK-DECISION.md`, and `docs/design.md` record them and
  `make check` passes.

## Never

Scaffold a framework before confirmation, ask questions one at a time across
many turns, or copy a reference product's names, assets, or copy.
