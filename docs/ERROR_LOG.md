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
| EL-006 | 2026-10-08 | Every web trial blocked by `unregistered product surface: index.html`, which no declaration could clear | A web generator writes its entry file at the repository root, but a surface owned exactly one path | `extra_paths`: a surface owns the files its generator put outside its directory, and the finding names the fix | `test_a_surface_owns_the_entry_files_its_generator_put_outside_it`, #57 | none |
| EL-007 | 2026-10-08 | `make done` printed `all must features evidenced` at 0% complete on a project with no features defined | Completeness tested the *open* must rows, and `all()` over an empty list is vacuously true; `feature_errors` guarded that state on `if rows`, so `make check` passed it | `countable()`; summary, `make next` and `feature_errors` all judge on countable rows | `test_a_list_with_nothing_countable_is_never_called_complete`, #55 | none |
| EL-008 | 2026-10-08 | `Untracked build output is not ignored` — `.next/` was committed by a trial and the scan flagged a generated chunk | The shipped ignore list covered `dist/` but not the frameworks that write a dot-prefixed build directory at the root | Every supported framework build directory is listed in `.gitignore`, under one comment naming the frameworks | `ShippedGitignoreTests`, #56 | none |
| EL-009 | 2026-10-08 | `make next` returned `Next (research)` on an adopted API after the work was finished and `make done` was green | `next_step` demanded cited URLs for every product while `research_errors` enforces that file only for UI kinds, and `make adopt`/`make init` wrote identical manifests so no rule could tell an adopted project from a new one | `make adopt` records `[kit].project_mode`; `next_step` skips research for an adopted project | `test_an_adopted_project_is_not_sent_to_competitor_research`, `test_adopt_records_that_the_product_existed_already`, #58 | none |
| EL-010 | 2026-10-08 | Three Haiku trials aborted after 1 turn at `$0.00` spend on `rateLimitType":"five_hour"` | Provider usage limit (`five_hour`, overage rejected at org level), not a kit fault: no kit command ran and no gate blocked | None in the kit; the trials read `main`, so they resume unchanged once headroom returns | `.agent/trials/20261008T072657Z-*/report.md`, comment on #21 | Operator gate: provider account usage headroom. Owner: TomSzenessy |

When adding an entry, link the issue, commit/PR, incident, and redacted evidence.
Do not include secrets, raw personal data, or unredacted provider/customer
exports. If the cause is still a hypothesis, keep the finding in the issue and
do not present it as a permanent fix.
