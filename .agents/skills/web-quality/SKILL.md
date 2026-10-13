---
name: web-quality
description: Audits and improves a web page or app for speed, Core Web Vitals (LCP, INP, CLS), accessibility, SEO and best practices, with measured before/after evidence; Use when asked to "audit my site", "run Lighthouse", "why is it slow", "fix LCP/CLS/INP", "improve page speed", "SEO check", or "accessibility audit", and before launching a web surface.
---

# Web quality

Measure first, change only what a measurement implicates, re-measure. Visual
review stays with `ux-quality` and `make ui-review`; this skill owns numbers. Without a runnable page, findings are **hypotheses**: name the
command that would confirm each and never claim a metric fails.

## Thresholds (75th percentile of real visits)

| Metric | Good | Needs work | Poor |
|---|---|---|---|
| LCP (load) | <= 2.5 s | <= 4 s | > 4 s |
| INP (responsiveness) | <= 200 ms | <= 500 ms | > 500 ms |
| CLS (stability) | <= 0.1 | <= 0.25 | > 0.25 |

Also: TTFB < 800 ms; contrast 4.5:1 text, 3:1 large text and controls; touch
or click targets >= 24 px (WCAG 2.2 minimum), 44 pt/48 dp on touch. Starting
budget for a content page, unless the project sets one: page < 1.5 MB,
JS < 300 KB, CSS < 100 KB, above-fold images < 500 KB, fonts < 100 KB,
third-party < 200 KB (compressed). Record any project budget in `docs/design.md` (created by `product-kickoff`; without it, in the issue).

## Audit order

1. **Scope:** exact URLs, states (public, signed in, empty, loaded), mobile
   first, desktop if it matters. Local or staging pages have no field data:
   missing is "unavailable", never "passing".
2. **Measure** (below). One trace and one Lighthouse run beat many dumps; save
   big reports to the scratchpad and keep only failing items in context.
3. **Rank** by user impact: broken or blocked (a11y barrier, console error,
   mixed content) > Core Web Vitals failure > page weight > SEO > polish.
4. **Fix** one cause at a time, smallest change, tied to a measured symptom.
5. **Re-measure** under identical conditions; keep a fix only if it beats the
   noise. A neutral change is a revert.
6. **Guard:** add a budget or Lighthouse assertion to CI if the owner wants one.

## Measure

- **Lab, local:** `npx lighthouse <url> --output=json --output-path=<scratchpad>/lh.json
  --only-categories=performance,accessibility,seo,best-practices --form-factor=mobile`
  (add `--preset=desktop` for desktop). Record URL, form factor, throttling,
  cold or warm cache. For a decision run three times; report median and range.
- **Playwright MCP** (enabled here, `docs/resources.md`): navigate, then
  `browser_snapshot` (accessibility tree, headings, labels), `browser_console_messages`
  (must be clean), `browser_network_requests` (sizes, third parties, failures),
  `browser_resize` to 375/768/1280 widths, `browser_take_screenshot`. For
  timings use `browser_evaluate` with `PerformanceObserver` for
  `largest-contentful-paint` and `layout-shift` (`buffered: true`) or a one-off
  Python Playwright script against the local server (`page.wait_for_load_state('networkidle')`
  before reading the DOM; headless chromium). One page session is a lab
  observation, not field data.
- **Accessibility:** Lighthouse plus axe-core (`npx @axe-core/cli <url>`),
  then manual: Tab through everything, 200% zoom, `prefers-reduced-motion`,
  a screen reader pass on the key flow. Automated tools find a minority of issues.
- **Field:** CrUX / PageSpeed Insights for a public URL; for production, the
  `web-vitals` library (attribution build) into the project's telemetry. Fixes
  show in field data only after new visits: say "pending".

## Fixes by symptom

**LCP**
- Slow TTFB: cache or CDN, drop redirects, fix slow queries and cold starts.
- Late discovery: the LCP image must be an `<img>` in the initial HTML with
  `fetchpriority="high"` (never `loading="lazy"`); preload only if the trace
  shows late discovery. Not a CSS background or client-rendered.
- Heavy file: AVIF/WebP, `srcset` + `sizes`, correct pixel dimensions.
- Render blocking: inline only proven critical CSS, `defer` scripts, no
  `@import`, remove unused CSS.
- Content appears after JS: SSR, static rendering, or streaming.
- Fonts: WOFF2, subset, `font-display: swap`, preload only the critical face.

**INP**
- Find the phase: input delay (main thread busy before the handler),
  processing (handler work), presentation (style/layout/paint after it).
- Split long tasks (> 50 ms) with `scheduler.yield()` or `setTimeout`; show
  visible feedback first, defer the rest.
- CPU-heavy work to a Web Worker; delay third-party widgets, facade embeds.
- Avoid layout thrash (batch reads before writes); virtualize lists over
  ~100 rows or use `content-visibility: auto` with `contain-intrinsic-size`.

**CLS**
- Every `<img>`/`<video>`/iframe has `width` + `height` or `aspect-ratio`.
- Reserve a fixed-size slot for ads, embeds, banners, async components; never
  insert content above what the user is reading.
- Fonts: match fallback metrics (`size-adjust`, `ascent-override`).
- Animate `transform` and `opacity`, not `top`/`height`/`margin`.

**Weight and caching**
- Hashed assets `Cache-Control: public, max-age=31536000, immutable`; HTML
  `no-cache`; Brotli or gzip on; HTTP/2 or 3.
- Code-split by route; import named exports, not whole libraries; delete
  unused dependencies; `async`/`defer` third-party scripts.
- Below-fold images `loading="lazy"`; `preconnect` only to early-used origins.
- Prerendering next pages (Speculation Rules, `eagerness: "moderate"`) is an
  optional enhancement for predictable journeys, Chromium-only; exclude
  logout and checkout, and gate analytics on `document.prerendering`.

## Accessibility checklist (WCAG 2.2 AA)

- Native elements before ARIA; buttons are `<button>`, links are `<a href>`;
  one `<main>`, a logical heading outline, `<html lang>`, skip link.
- Every control has an accessible name; every input a visible `<label>`; errors
  are text, linked via `aria-describedby`, and announced (`role="alert"` or a
  live region).
- Informative images have `alt`; decorative `alt=""`; no colour-only meaning.
- Visible focus never hidden behind sticky bars; no keyboard trap; modals trap
  and restore focus; Esc closes.
- No drag-only action; login allows paste and password managers.

## SEO and best practices

- Unique `<title>` and meta description per page, one `<h1>`-led outline,
  descriptive link text, canonical URL, `viewport` meta, crawlable
  `robots.txt` that does not block CSS/JS, sitemap of indexable URLs only,
  JSON-LD only for content actually on the page. No ranking promises: indexing
  results are pending.
- HTTPS only, no mixed content; verify deployed response headers (CSP with
  `frame-ancestors`, HSTS once all subdomains are HTTPS, `X-Content-Type-Options`,
  `Referrer-Policy`), not just config. No source maps or secrets in production
  bundles. Secrets, dependency, and input rules: `docs/security.md`.
- Clean console, valid doctype, `<meta charset>` first, passive scroll/touch
  listeners, no `document.write` or synchronous XHR, permission prompts asked
  in context.

## Report

Evidence table first (signal, scope and conditions, baseline, after, source),
then: measured failures, trace-backed causes, source hypotheses, fixes made,
verification status (re-run done, manual checks done, field pending). Cite
`path:line`. Run `make ui-review` for the visual pass; `make done` before
claiming complete. Refuse "fast on my machine" (throttle to mobile) and "obviously
faster" (unmeasured means unknown).

Upstream depth: `make upstream ID=addyosmani-web-quality-skills` lists pinned files (e.g. LCP → LCP.md); fetch only the one your step needs.
