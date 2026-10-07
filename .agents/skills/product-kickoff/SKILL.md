---
name: product-kickoff
description: "Turns 'build me an app/site/game' into confirmed decisions before any code: asks the owner a short round of questions with recommendations (users, platforms, stack, visual style, onboarding, data), shows two or three mockup directions, and records the choices. Use at the start of every new product or major reshaping."
---

# Product kickoff

Outcome: before any product code, the owner has confirmed who it is for, the
platforms, the stack, and a visual direction they have seen; research, a
feature list with acceptance criteria, and the decisions are recorded where
every later agent finds them. Then `make next` drives the build to launch.

## 1. Understand before asking

- Read `VISION.md` and `docs/STACK-DECISION.md`. If they are already accepted,
  this is a reshape: ask only about what changes, then update both and record
  the change as an ADR; never silently overwrite a confirmed decision.
- Restate the idea in one sentence and name the riskiest assumption.
- **Size it:** `prototype` (days, throwaway or demo), `product` (an MVP for
  real users), or `platform` (many users, teams, or services). The tier sets
  how much `stack-foundation` and `docs/engineering.md` "Built to scale"
  apply; never build platform machinery for a prototype.
## 2. Research the space (always)

Delegate to the `researcher` role (web search and browser) and write
`docs/product/research.md` with cited URLs (`make check` needs at least three):

- **Comparable products:** the three to five best, what each does well, and
  what to borrow. For a named reference, run `product-recon`.
- **What users hate:** `review-mining` on their reviews; each complaint is a
  feature or a differentiator.
- **Design references:** apps or sites whose look and feel fit the brief
  (screenshots in ignored `.agent/references/`), and what to borrow from each.
- **Our angle:** the one thing this product will do better.

Bring the findings into the questions as recommendations.

## 3. Ask one round of questions

Ask everything in one message (use the host's question tool when it has one).
Give each question options and your recommendation, so "go with your picks"
is a valid answer. Ask only what changes direction:

1. **Users and goal:** who, which problem, what success looks like (one metric).
2. **Platforms:** web, iOS, Android, desktop; offline needed?
3. **Stack:** an existing codebase or a stack the owner already uses wins.
   Otherwise recommend from platforms, team skills, tier, and constraints.
   Defaults to start from (before scaffolding, have the `researcher` role or
   Context7 confirm the choice is still recommended and get current versions):

   | Need | Default | Consider instead |
   |---|---|---|
   | Web app | React + Next.js + Tailwind (+ shadcn/ui) | SvelteKit; Astro for content sites |
   | iOS + Android, one codebase | Expo (React Native) | Flutter for highly custom, pixel-identical UI |
   | Best native feel, one platform | SwiftUI / Jetpack Compose | — |
   | Desktop app | Tauri (small, web UI) | Electron for Node-heavy needs; native toolkits |
   | Game | Web canvas or Phaser for small 2D; Godot (open source) for 2D/3D | Unity or Unreal for console or high-end 3D (check license terms) |
   | API, CLI, or data/ML | The team's strongest language; Python for data and ML; TypeScript or Go for services | — |
   | Backend | Managed (e.g., Supabase or Firebase) for `prototype` and `product` | Own services with Postgres, queues, and caches at `platform` tier |

4. **Visual style:** platform-native (Apple HIG, Material 3) or a custom brand;
   two or three apps or sites they like and why; mood words; light, dark, or
   both; existing logo or colours.
5. **First-run and core flow:** what a new user does in the first minute;
   is sign-up needed before value?
6. **Data, accounts, payments, privacy:** sign-in method, payments, children
   or health data, regions; personal data means `docs/privacy.md`.
7. **Constraints:** budget, deadline, hosting, must-use services, languages.

Ask a second round only if an answer opens a new high-impact choice. Never
assume answers: if you cannot ask (headless run, tool unavailable) or the owner
has not answered, write the questions with your recommendations in your reply
(and the kickoff issue when one exists), then stop. That is a correct, finished
outcome. Only an explicit "use your picks" counts as approval.

## 4. Show mockups before building

- Produce two or three clearly different directions for the one or two most
  important screens (usually first-run and the main screen), with the same
  content so only the design differs. Static HTML + Tailwind renders anywhere;
  use platform previews when the stack is native.
- Render them at phone and desktop sizes with the browser tool (Playwright
  MCP), check them against `ux-quality` yourself, then show the screenshots to
  the owner with a one-line rationale per direction. If `make capabilities`
  shows no browser, give the owner the file paths to open instead.
- Iterate on the chosen direction once or twice. Keep mockups in ignored
  `.agent/mockups/` unless the owner wants them in the repository.

## 5. Define the product and plan delivery

- **Feature list:** write `docs/product/features.csv` (feature, area, priority,
  status, evidence, acceptance, source) from the owner's goal, the research,
  and the competitor complaints, then append the rows of
  `production-features.csv` (this folder) that apply. "Complete" means every
  must row is `yes` with evidence; a demo-sized list is a defect.

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

## 6. Record and hand off

- `VISION.md` (status accepted), `docs/STACK-DECISION.md` (decision, rejected
  alternatives, and why).
- `make new KIND=doc NAME=design GROUP=design DESC="Visual direction, tokens, and UX principles; before any UI work"`,
  then fill it with the chosen direction, references, and tokens (the
  `design-tokens` conventions and contrast checker apply).
- File the epic and slice issues, then run the `stack-foundation` skill for
  the walking skeleton; its surface's quality oracle includes the `ux-quality`
  review. Then follow `make next` slice by slice until it reports the launch
  phase; never stop at a green `make done` while must features are open.

## Done when

- The owner explicitly confirmed platforms, stack, and one mockup direction.
- `docs/product/research.md` cites the comparable products, complaints, and
  design references; `docs/product/features.csv` covers them plus the
  production rows, each must row with an acceptance criterion.
- An epic with ordered slice issues exists, starting with the walking skeleton.
- `VISION.md`, `docs/STACK-DECISION.md`, and `docs/design.md` record them and
  `make check` passes.

## Never

Scaffold a framework before confirmation, ask questions one at a time across
many turns, or copy a reference product's names, assets, or copy.
