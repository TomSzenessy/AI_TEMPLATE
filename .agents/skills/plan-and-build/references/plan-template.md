# Plan template

Post as an issue comment (or in the `Local-WAL` draft). Open it from
plan-and-build step 3.

```markdown
## Plan: <feature> (design: #<issue>)
Goal: <one sentence>. Approach: <2-3 sentences>.
Global constraints: <version floors, naming, copy rules; exact values, one per line>
Review focus: <up to 5 inputs or failure modes the design implies that no task
exercises; each gets a test in the task that owns the code>

### File map
- `path/a.py` - <one responsibility> (create | modify)

### Task 1: <vertical slice, verb phrase>   [S|M]  depends on: none
Files: create `...`, modify `...:120-145`, test `tests/...`
Consumes: <exact signatures from earlier tasks>   Produces: <exact names/types later tasks use>
Acceptance:
- [ ] <specific, testable condition>
Steps:
- [ ] Failing test `test_name`: <assertions with the real expected values>
- [ ] Run `<command>`; expected: FAIL with `<message>`
- [ ] Implement `fn(arg: T) -> R` in `path`; <one line only if a choice remains>
- [ ] Run `<command>`; expected: PASS
- [ ] Commit `<type>: <summary>` (cite the issue)

### Checkpoint after tasks 1-3
- [ ] `make done` green  - [ ] core flow works end to end  - [ ] criteria so far met

### Risks
| Risk | Impact | Mitigation |
```

Checklist before posting: every design criterion maps to a task; no task over
~5 files or needing "and" in its title; each task has a verification command;
signatures agree across tasks; riskiest slice early; the plan decides only
what an implementer cannot decide alone.
