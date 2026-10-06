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
| `replica-diff/` (SKILL.md, `parity.py`, `imgdiff.py`) | [`parity-check`](./.agents/skills/parity-check/) | Same generalization; two crash-on-malformed-input defects hardened (short IHDR chunk, zero-width PNG); `parity.py`/`imgdiff.py` keep their CLI contracts. |
| `replica-design/` (SKILL.md, `contrast.py`, `tokens.json`) | [`design-tokens`](./.agents/skills/design-tokens/) | Same generalization; `contrast.py` unchanged apart from attribution and path examples. |
| `replica-entrepreneur/` (SKILL.md, `reviews.py`, `themes.json`) | [`review-mining`](./.agents/skills/review-mining/) | Same generalization; ragged-CSV row handling hardened in `reviews.py`. |
| `replica-brand/` (SKILL.md, `sweep.py`) | [`brand-sweep`](./.agents/skills/brand-sweep/) | Naming/checklist and sweep parts kept; logo/voice/palette brief trimmed to what the template needs; `sweep.py`'s `--include-replica` flag generalized to `--include-reference`. |

Upstream material not adopted here, reviewed and declined for this template:
`replica-architect`, `replica-build`, `replica-backend`, `replica-test`,
`replica-launch`, `replica-deploy`, and `listing.py` (store-listing linter,
coupled to App Store/Google Play metadata). Reasons are recorded in
[`docs/skills.md`](./docs/skills.md).

Test suites in `.agents/skills/*/tests/` are adapted from upstream `tests/`
with regression tests added for the hardened defects. Files adapted for this
repository carry SPDX headers identifying the upstream source and revision.

## License

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
