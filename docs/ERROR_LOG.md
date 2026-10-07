# Error ledger

<!-- index: operate | Solved failure signatures and permanent fixes | A recurring failure needs a durable regression/fix record. -->

This is a compact record of solved or recurring operational failure signatures.
It is not a backlog. Unresolved work and priorities live in GitHub Issues.

Each row starts with a stable key (`EL-001`) so a failing check or a later
incident can name the signature it repeats. The backticked spans in the symptom
are the literals a finding is matched against, and the permanent-fix cell is what
`make check` reports when it matches; a fresh failure matches nothing and is
reported as itself.

| Key | Date | Signature / symptom | Confirmed cause | Permanent fix | Regression evidence | Residual gate / owner |
|---|---|---|---|---|---|---|
| EL-001 | 2026-10-07 | Fresh project's `make done` fails in the kit's own tests | Template-only tests (trial, adopt, init) ran in derived projects | `template_only` skip; the golden-path test runs the kit suite inside a fresh project | `GoldenPathTests`, PR #11 | none |
| EL-002 | 2026-10-07 | `covers pattern matches no file: .agents/trials/**` right after init | Pruning template material left doc bindings pointing at it | `localize_text` drops bindings to pruned material in init, adopt, and kit-update | `TrialTests`, `AdoptTests`, PR #11 | none |
| EL-003 | 2026-10-07 | `make check` starts failing a year later on an unchanged repo | Record and review ages (vision, stack, skills, critic evidence, issue dates) blocked every phase | Ages gate releases only; `make test-future` runs the suite 800 days ahead in CI | #10, `make test-future`, PR #11 | none |
| EL-004 | 2026-10-07 | `Docs-Unaffected: tools/** untouched` exempted every doc | A path-like scope was read as a reason, which means "all docs" | A non-document path or glob scope exempts nothing | `test_non_document_scope_exempts_nothing`, PR #11 | none |
| EL-005 | 2026-10-07 | Every trial blocked by `unregistered product surface: tests` (or `e2e`, `test-results`, `examples`) | Test and example folders were not implicit infrastructure | Infrastructure by default; `scripts/` and `config/` still need a declaration | #13 | none |

When adding an entry, link the issue, commit/PR, incident, and redacted evidence.
Do not include secrets, raw personal data, or unredacted provider/customer
exports. If the cause is still a hypothesis, keep the finding in the issue and
do not present it as a permanent fix.