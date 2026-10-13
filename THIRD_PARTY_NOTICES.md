# Third-party notices

This repository vendors and adapts material from
[Jakeschincariol/replica-skill](https://github.com/Jakeschincariol/replica-skill),
used under the MIT License below. The pinned upstream revision is
`77c9436fb3d18c3d58169efb8caf4fe906b0dc51` ("The Replica skill: 11 Claude
skills, v1.0"). Reviewed and adapted 2026-10-06 under issue #3.

## What was adapted

| Upstream | Local | Adaptation |
| --- | --- | --- |
| `replica-recon/` (SKILL.md, `recon-map.md`, `features.csv`) | [`product-recon`](./.agents/skills/product-recon/) | Generalized from app cloning to studying any reference product; artifact root `replica/` → `reference/`; pack-chain references retargeted. |
| `replica-diff/` (SKILL.md, `parity.py`, `imgdiff.py`) | [`parity-check`](./.agents/skills/parity-check/) | Same generalization; three malformed-input defects hardened (short IHDR chunk and zero-width PNG in `imgdiff.py`, ragged CSV rows in `parity.py`); the tools' CLI contracts keep their documented exit codes. |
| `replica-design/` (SKILL.md, `contrast.py`, `tokens.json`) | [`design-tokens`](./.agents/skills/design-tokens/) | Same generalization; `contrast.py` unchanged apart from attribution and path examples. |
| `replica-entrepreneur/` (SKILL.md, `reviews.py`, `themes.json`) | [`review-mining`](./.agents/skills/review-mining/) | Same generalization; ragged-CSV row handling hardened in `reviews.py`. |
| `replica-brand/` (SKILL.md, `sweep.py`) | [`brand-sweep`](./.agents/skills/brand-sweep/) | Naming/checklist and sweep parts kept; logo/voice/palette brief trimmed to what the template needs; `sweep.py`'s `--include-replica` flag generalized to `--include-reference`. |

Upstream material not adopted here, reviewed and declined for this template:
`replica-architect`, `replica-build`, `replica-backend`, `replica-test`,
`replica-launch`, `replica-deploy`, and `listing.py` with `listing.example.json`
(store-listing linter, coupled to App Store/Google Play metadata). Reasons are
recorded in [`docs/skills.md`](./docs/skills.md). Upstream `tests/test_repo.py`
(pack-shape checks) and the listing half of `tests/test_contrast_listing.py`
were dropped with the tools they cover.

Test suites in `.agents/skills/*/tests/` are adapted from upstream `tests/`
with regression tests added for the hardened defects. Files adapted for this
repository carry SPDX headers identifying the upstream source and revision.


## Workflow material distilled from public skill collections

Reviewed 2026-10-13 under issue #100. These sources were read in full at the
pinned revisions below; their ideas were merged by trigger and rewritten in
this repository's voice, so no local file is a copy of an upstream file.
Local skills carry no per-file notices; this section is the single record.

| Upstream (pinned revision) | License | Local owners it shaped |
| --- | --- | --- |
| [obra/superpowers](https://github.com/obra/superpowers) `bb92a77` | MIT, (c) 2025 Jesse Vincent | `plan-and-build`, `systematic-debugging`, `review-practice`, `docs/skills.md` |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) `1be8e34` | MIT, (c) 2025 Addy Osmani | `plan-and-build`, `systematic-debugging`, `review-practice`, `stack-foundation`, `docs/engineering.md`, `docs/security.md`, `docs/verification.md`, `docs/resources.md`, `docs/adr/README.md` |
| [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills) `afa8da9` | MIT, (c) 2026 Addy Osmani | `web-quality` |
| [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) `2e08b91` | Apache-2.0, Copyright 2026 Julius Brussee (upstream `NOTICE`: "Caveman / Copyright 2026 Julius Brussee") | `review-practice` (finding format), `docs/engineering.md` |
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) `c63b8dd` | Apache-2.0 | `ux-quality` (anti-pattern list, audit/critique/polish vocabulary) |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) `be2a406`, `webapp-testing` | Apache-2.0 | `web-quality` (one testing line) |

Change statement for the Apache-2.0 sources (Caveman, Impeccable, webapp-testing): guidance was condensed and
rewritten; no file, code, or asset was copied. License text:
<https://www.apache.org/licenses/LICENSE-2.0>.

The other reviewed collections (Ponytail, Archify, Graphify, Understand
Anything, UI UX Pro Max, vercel-labs/skills, REA, API Anything) are linked as
routes in [`resources.toml`](./resources.toml), not copied.

The MIT License text below applies to each MIT source above (Superpowers and
both Addy Osmani repositories), with its own copyright line from the table.

## License (replica-skill; same MIT text for the sources above)

Copyright (c) 2026 Jake Schincariol

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
