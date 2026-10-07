# Documentation that tracks the code

<!-- index: operate | Doc-code bindings, staleness, owed docs, and the Docs-Unaffected trailer | A document and its code drift apart, or a commit must exempt a document. -->
<!-- covers: tools/kit/docsync.py tools/kit/docmeta.py -->

A document declares what it describes with one comment near its top, such as
`<!-- covers: src/billing/** docs/api/billing.yaml -->` (repository globs:
`*`, `?`, `**`). From that single declaration:

- `make where Q="<path or term>"` and the after-edit hook name the owning doc.
- **Dead binding** (a glob matches no file): the code moved or died, so
  `make check` fails until the binding follows it.
- **Stale document**: a commit newer than the document's last commit touched
  covered paths. `make check` fails. A commit authored by `dependabot[bot]` whose diff changes only
  `uses:` lines is ignored (a bot cannot add a trailer); any other change is not. If a change truly does not affect the doc,
  record that in the commit with a trailer, `Docs-Unaffected: docs/x.md <reason>`
  (a reason with no path exempts all documents; a value that starts with a
  non-document path or glob, such as `tools/** untouched`, exempts nothing). Git's own trailer parsing is
  used everywhere: trailers belong in the message's last paragraph, and a
  trailer without a reason exempts nothing.
- **Owed document**: covered paths changed on this branch while the doc did not;
  the stop gate and `make done` report it before history even exists. Both honour
  the trailers on the commits they judge (`docsync.owed_since`).
- **Command references**: every backticked `make <target>` or `repoctl <command>`
  in Markdown, and every `make` line in a code fence, must exist. A `make`
  reference resolves to the nearest Makefile above the document (and the
  files it includes, such as `kit.mk` after `make adopt`), so subprojects and
  trial seeds keep their own targets.

Bind documents that explain behavior (architecture, module cards, runbooks, API
notes). Pure policy documents need no binding. Staleness needs full history:
CI checks out with `fetch-depth: 0`, and shallow clones skip it.

This page owns the rules a binding carries. The gates that enforce them — when
`make check` blocks, what the commit gate and `make done` judge — are in
[`self-healing.md`](./self-healing.md).
