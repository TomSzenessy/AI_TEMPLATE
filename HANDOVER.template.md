# Session handover

Copy this file to the ignored root-level `HANDOVER.md` when substantial work may
continue in another session, branch, machine, or model. It supplements the
issue-backed write-ahead record; it is not a second task register. Keep the live
file concise, current, and free of credentials, tokens, raw personal data, and
unnecessary exports. The committed cross-machine variant is
[`docs/handoffs/TEMPLATE.md`](./docs/handoffs/TEMPLATE.md); both use the same
sections.

## Objective

State the outcome that matters and why it matters now.

## Current state

- **Created (UTC):** `<timestamp>`
- **Next actor/session focus:** `<one sentence>`
- **Committed baseline:** `<branch/commit or issue links>`
- **Working tree:** `<clean or exact uncommitted paths>`
- **Done:** `<verified facts>`
- **Remaining:** `<smallest next slice>`

## Evidence already collected

| Check / artifact | Result | Date/command | Evidence type |
|---|---|---|---|
| `<command or render>` | `<observed result>` | `<UTC/command>` | `source/test/deployed/provider/hardware/counsel` |

## Decisions and constraints

Reference ADRs/issues. Record only decisions the next actor must honor and the
reason, not a general design essay.

## Blockers and open questions

State confirmed blockers, hypotheses, owners/gates, and the next experiment.
Use `N/A — none`.

## Exact next action

1. `<one command or edit>`
2. `<observable checkpoint>`

## Relevant paths and issues

Link only the files, issues, PRs, and external references needed to continue.
Do not paste their contents.

## Verified skill suggestions

Name an installed/reviewed skill, why it applies, and its source/revision.
Otherwise write `none`. Never suggest blind installation.

## Redaction and retention check

Confirm no secrets, credentials, raw personal data, full exports, or unnecessary
user identifiers are present. State where the record may be shared and when it
can be deleted.
