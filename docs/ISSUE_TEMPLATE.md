# Canonical issue record

GitHub Issues are the live task, status, and evidence register. This file defines
the minimum shape for a new or materially updated issue. Search open and closed
issues by title, symptom, path, and topic before filing; update the existing
record when the root cause and acceptance boundary match.

## Duplicate check

Record one line in the issue:

```text
Duplicate check: searched title, symptom, and path for <terms/files>; reused #N | no duplicate found
```

A new issue is justified only for an independent root cause, owner/gate, or
deliberate reopening. Link the predecessor and explain the split.

Native forms are lightweight intake in `agent-first`; an agent or maintainer
adds the canonical labels during triage. The `repoctl issue` path always emits
the full required label set. In `regulated`, use the validated CLI/private
route rather than native forms so the review-evidence and disclosure gates are
not bypassed.

## Classification

Use exactly one label from each required family:

| Family | Allowed values |
|---|---|
| `type:*` | `bug`, `security`, `privacy`, `compliance`, `audit`, `task`, `operations`, `documentation`, `enhancement` |
| `priority:*` | `P0`, `P1`, `P2`, `P3` |
| `area:*` | `security`, `privacy`, `legal`, `operations`, `platform`, `documentation`, `web`, `game`, `media`, `data`, `repo` |
| `topic:*` | one stable lowercase kebab-case topic |
| `status:*` | `triage`, `ready`, `in-progress`, `blocked`, `fixed`, `wont-fix` |
| `gate:*` | optional: `operator-action`, `counsel-review`, `provider-evidence`, `deployment-evidence`, `hardware-validation` |
| `surface:*` | optional: `repo`, `web`, `game`, `media`, `backend`, `data`, `docs`, `provider`, `deployment` |

`ready` means a runnable reproduction or validation experiment exists. External
work remains `blocked` with its gate and named owner. The public `repoctl issue`
adapter refuses `type: security`; use the private route in
[`../SECURITY.md`](../SECURITY.md), then file a redacted follow-up only after
coordinated disclosure. A unit test never proves deployment, provider
propagation, hardware behavior, or legal approval.

## Required body

`[governance].profile = "regulated"` preserves the full headings below. The
default `agent-first` profile requires the compact contract: `Summary`,
`Acceptance criteria`, `Evidence`, `Disclosure classification`, and
`Dependencies and handoff`; add the diagnostic headings when they help a
reviewer. `minimal` delegates the issue contract to the host organization.
Replace placeholders; write `N/A — reason` when a section genuinely does not
apply.

### Summary

One sentence: concrete symptom or outcome and impact.

### What happens

- **Observed:**
- **Expected:**
- **Affected subject/surface:**

### Where

- **Entry point / surface:**
- **Paths, components, data, or environment:**
- **Evidence location:**

### When

- **Preconditions:**
- **Sequence, race, or timing:**
- **Frequency:** `always`, `intermittent`, or `once observed`
- **First observed / last known good:**

### Why

- **Root-cause status:** `confirmed`, `likely`, or `open question`
- **Cause and contributing factors:**
- **Why it matters now:**

### How to reproduce

Give the smallest deterministic steps or validation experiment.

1. [Starting fixture/environment.]
2. [Exact action.]
3. [Observable result and where to inspect it.]

- **Actual result:**
- **Expected result:**
- **Evidence captured:**
- **Cleanup / rollback:**

### Impact and scope

- **Impact / risk:**
- **In scope:**
- **Out of scope / linked residual:**

### Acceptance criteria

Use objective checkboxes and name the evidence for each. Include a regression
or negative case, relevant contract/migration checks, and a real artifact or
state observation where applicable.

- [ ] [Criterion and evidence.]
- [ ] [Negative/failure case.]
- [ ] [External provider/deployment/hardware/counsel evidence, or N/A.]

### Evidence

Mark every item as `source`, `test`, `deployed`, `provider`, `hardware`, or
`counsel`; redact secrets and personal data.

### Disclosure classification

- **Public-safe:** yes
- **Security/privacy review:** `not applicable` or link the private review record
- **Reviewer/date:** `[REQUIRED for public filing]`

This is an explicit publication gate, not a legal conclusion. A body containing
an unpatched vulnerability, exposed secret, raw personal data, or sensitive
provider detail belongs in the private route in [`../SECURITY.md`](../SECURITY.md),
not in a public Issue.

### Dependencies and handoff

- **Owner / next action:**
- **External dependency:** `none` or named owner/gate
- **Linked issue / follow-up:**
- **Risk of leaving unresolved:**

## Resolution record

Complete only when the issue is ready to close:

- **Root cause and final change:**
- **PR / commit / artifact:**
- **Verification performed and observed results:**
- **Residual risk / operational action:**
- **Closed on (UTC):**

## Small update

```text
Status: <old> → <new>
Owner: <name/team>
Next: <one concrete action>
Evidence: <link or command>
Blocker: <dependency or none>
```
