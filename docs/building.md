# Building a product

<!-- index: operate | Product driver: feature list, research record, make next phases, product done, UI review | building or judging a product -->
<!-- covers: tools/kit/product.py tools/kit/uireview.py .agents/skills/product-kickoff/production-features.csv -->

Repository hygiene checks prove the code is tidy; they cannot prove the product
is complete or good. Everything on this page is the `product` pack
(`.agents/packs/product.md`, on by default; a repository that ships no product
switches it off — [`capabilities.md`](./capabilities.md)). This document owns the mechanics that do: a researched
feature list with evidence, a deterministic next step, a product-level done
score, and screenshot reviews. Skills say *how*; these checks make sure the
steps happen.

## The path: `make next`

`make next` reads repository state and prints one step, the skill or role to
use, and how to verify it. The session brief shows the same step. Phases, in
order:

| Phase | Done when |
|---|---|
| intake | `VISION.md` is accepted after the `product-kickoff` questions; `docs/design.md`, `docs/product/research.md`, and `docs/product/features.csv` are created by `product-kickoff` |
| research | `docs/product/research.md` cites at least three sources |
| features | `docs/product/features.csv` exists with must rows |
| design (UI) | `docs/design.md` records the chosen mockup direction |
| stack | `docs/STACK-DECISION.md` says `Status: accepted` |
| skeleton | a product surface is declared (`stack-foundation`) |
| preview (web UI) | the surface has a `[surfaces.preview]` table (native apps use simulator screenshots) |
| build | every must feature is `yes` with evidence |
| review (UI) | the latest entry in `docs/product/ui-reviews.md` matches the code and the verdict is `pass` |
| polish | every should feature is done or skipped |
| launch | release sequence in [`production.md`](./production.md) |

Keep looping (`make next`, build, `make done`) until the launch phase. A green
`make done` with open must features means the slice is done, not the product.
What changed in `tools/kit/product.py` last: `docs/design.md` and
`docs/STACK-DECISION.md` are read through the shared name constants in
`tools/kit/names.py`; the phases above are unchanged.

## Feature list: `docs/product/features.csv`

Columns: `feature, area, priority (must|should|could), status
(yes|partial|no|skip), evidence, acceptance, source`. Weights match
`parity-check`: must 3, should 2, could 1; yes counts 1, partial 0.5. This is
the one matrix: `product-recon` appends the reference product's features and
`review-mining` its fix-plan rows (`source` names the skill, `status` starts at
`no`), and `parity-check` and `make next` read the same file; `reference/` holds
recon evidence only. Kickoff
writes it from the owner's goal, the research, and competitor complaints, then
appends the applicable rows of
[`production-features.csv`](../.agents/skills/product-kickoff/production-features.csv)
(onboarding, every screen state, accessibility, identity, undo, backup, error
handling, deployment, performance, and more), which is what turns a demo into a
product. `make check` fails when the list has no must row, a must row has no
acceptance criterion, or a `yes`/`partial` row cites anything that is not an
existing file; a must row marked `yes` also needs a test file or
`docs/product/ui-reviews.md` among its evidence, so citing `README.md` cannot
close a feature. `make done` prints the completeness score and
the open must features.

## Research: `docs/product/research.md`

Comparable products, real user complaints (`review-mining`), design references,
and the product's angle, each with a URL, under an `<!-- index: -->` line.
`make next` asks for it in every product; `make check` enforces at least three
cited sources once a UI product has a surface.

## UI review

`make ui-review` starts each UI surface's preview, captures every route at phone
(390x844) and desktop (1440x900) sizes in light and dark mode, plus any seeded
storage states. It uses an installed `playwright` CLI when one is on `PATH`
(CI images and cloud containers ship one with matching browsers), otherwise
`npx playwright@<[kit].playwright_version>`; setting that key pins it always.
The installed Chrome is used when present, otherwise Chromium
(`npx playwright install chromium`):

```toml
[surfaces.preview]
command = ["npm", "run", "dev", "--", "--port", "{port}", "--strictPort"]
url = "http://localhost:{port}"
routes = ["/", "/settings"]
states = { "with-data" = "app/review-states/with-data.json" }
```

`{port}` is replaced by a free port on every run, and the review refuses to
start if something already answers at the URL: a first trial screenshotted a
different project's dev server that held the port.

Screenshots stay local in `.agent/reviews/<run>/`; the review record is
appended to the tracked `docs/product/ui-reviews.md`: the reviewed code digest
per surface, the screenshot list, findings, and `Verdict: pending`. Whoever
looked at the images (you or the `critic` role) records findings and sets
`Verdict: pass` or `Verdict: fix`; `fix` never clears anything.

The review gates outcomes, not commits ([when a check may block](./self-healing.md#when-a-check-may-block)):

- **Per feature:** a must UI feature is `yes` only when its evidence cites
  `docs/product/ui-reviews.md` (or a test), and `make next` holds the `review`
  phase until the latest review matches the code and passes.
- **Per release:** `make readiness` (from `phase = "private-preview"` on)
  fails while any web UI surface was never reviewed, changed since its latest
  review, or is not `pass`.
- **Per change:** `make done` only *mentions* a stale review, so a one-line CSS
  fix does not need a screenshot run.

Because the record is tracked, every clone and CI sees the same review state;
the review regenerates the docs index itself, so a first review never fails
`make check`.
