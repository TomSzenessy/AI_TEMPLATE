# Error ledger

<!-- index: operate | Solved failure signatures and permanent fixes | A recurring failure needs a durable regression/fix record. -->

This is a compact record of solved or recurring operational failure signatures.
It is not a backlog. Unresolved work and priorities live in GitHub Issues.

Each row starts with a stable key (`EL-001`) so a failing check or a later
incident can name the signature it repeats. The row contract — stable
`EL-###` key, backticked literals in the symptom, cited regression test — and
how `make check` matches a finding to a row are defined in
[`operations.md`](./operations.md#the-error-ledger).

| Key | Date | Signature / symptom | Confirmed cause | Permanent fix | Regression evidence | Residual gate / owner |
|---|---|---|---|---|---|---|
| EL-001 | 2026-10-07 | `fails in the kit's own tests` after a fresh project's `make done` | Template-only tests (trial, adopt, init) ran in derived projects | `template_only` skip; the golden-path test runs the kit suite inside a fresh project | `GoldenPathTests`, PR #11 | none |
| EL-002 | 2026-10-07 | `covers pattern matches no file: .agents/trials/**` right after init | Pruning template material left doc bindings pointing at it | `localize_text` drops bindings to pruned material in init, adopt, and kit-update | `TrialTests`, `AdoptTests`, PR #11 | none |
| EL-003 | 2026-10-07 | `review older than a year` (and every other age gate) fails `make check` a year later on an unchanged repo | Record and review ages (vision, stack, skills, critic evidence, issue dates) blocked every phase | Ages gate releases only; `make test-future` runs the suite 800 days ahead in CI | #10, `make test-future`, PR #11 | none |
| EL-004 | 2026-10-07 | `Docs-Unaffected: tools/** untouched` exempted every doc | A path-like scope was read as a reason, which means "all docs" | A non-document path or glob scope exempts nothing | `test_non_document_scope_exempts_nothing`, PR #11 | none |
| EL-005 | 2026-10-07 | Every trial blocked by `unregistered product surface: tests` (or `e2e`, `test-results`, `examples`) | Test and example folders were not implicit infrastructure | Infrastructure by default; `scripts/` and `config/` still need a declaration | `test_test_and_example_folders_are_infrastructure_by_default`, #13 | none |

When adding an entry, link the issue, commit/PR, incident, and redacted evidence.
Do not include secrets, raw personal data, or unredacted provider/customer
exports. If the cause is still a hypothesis, keep the finding in the issue and
do not present it as a permanent fix.
