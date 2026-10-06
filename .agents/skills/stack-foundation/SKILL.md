---
name: stack-foundation
description: "Sets up a new surface so it is clean, observable, and shippable from day one: official generator, strict types, lint and format, unit and end-to-end tests, CI wiring, environment config, preview deploys, error tracking, and rot finders. Use right after product-kickoff confirms the stack, or when adding a new surface."
---

# Stack foundation

Outcome: a walking skeleton (the thinnest end-to-end path, deployed to a
preview) whose quality gates run in `make done` and CI before any feature work.
Cleanliness is cheapest on day one; retrofitting it costs ten times more.

## Steps

1. **Scaffold with the official generator** at a pinned version (for example
   `create-next-app`, `create-expo-app`, `flutter create`, the Xcode or Android
   Studio template). Verify the current command and version with Context7 or the
   `researcher` role first. Keep generated defaults unless the decision record
   says otherwise.
2. **Strictness on:** strict type checking (TypeScript `strict`, Dart analysis,
   Swift warnings as errors), one formatter, one linter, no warnings in CI.
3. **Tests at three levels:** a unit test runner, one end-to-end smoke test of
   the walking skeleton (Playwright for web, Maestro or Detox for mobile, XCUITest
   for native), and the screenshot review from `ux-quality`.
4. **Declare the surface** in `project.toml`: `verification` runs typecheck,
   lint, and tests; `garden` runs a dead-code finder (knip for JS/TS, vulture for
   Python, or the stack's analyzer); add a `[budgets]` glob so files stay agent-sized.
   Bind the surface's architecture doc with `<!-- covers: -->`.
5. **Configuration and secrets:** commit `.env.example` with every variable and
   a comment, never real values; validate configuration at startup and fail fast.
6. **Observability:** structured logs with request IDs, error tracking (for
   example Sentry or the platform's crash reporting), and a health endpoint for
   services. Record any personal data they touch in `docs/legal/data-inventory.md`.
7. **Delivery:** CI runs `make verify`; every pull request gets a preview
   deployment or build when the platform supports it; document rollback in
   `docs/production.md`.
8. **Web reach, if web:** semantic HTML, metadata and social cards, sitemap,
   performance budget (Core Web Vitals), and i18n-ready strings when more than
   one language is plausible.

## Done when

The walking skeleton is deployed to a preview, `make done` runs every gate
above and passes, and a fresh agent can find the surface with `make where`.

## Never

Hand-roll what the official generator provides, add a dependency without a
reason in the issue, or commit secrets, generated build output, or caches.
