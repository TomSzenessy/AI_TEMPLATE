# Data inventory and processing register

Project: `[REPLACE_WITH_PROJECT_NAME]`
Date: `[YYYY-MM-DD]`
Reviewer: `[name/team]`

**Status:** uninitialized working record. Replace each row with verified facts;
use `N/A — reason` when a field truly does not apply. This document is not a
formal Article 30 record or legal conclusion.

| Activity / purpose | Data subjects | Data categories | Source | System / region | Recipient / role | Retention trigger and maximum | Deletion / export path | Legal basis / exception | Evidence / owner |
|---|---|---|---|---|---|---|---|---|---|
| `[REQUIRED: activity]` | `[REQUIRED]` | `[REQUIRED]` | `[REQUIRED]` | `[REQUIRED]` | `[REQUIRED]` | `[REQUIRED]` | `[REQUIRED]` | `[counsel validation]` | `[source/test/provider/counsel]` |

## Browser and device state

| Name | Purpose | Provider | Type | Duration | Necessary or optional | Consent/withdrawal behavior | Evidence |
|---|---|---|---|---|---|---|---|
| `[REQUIRED or “none verified”]` | — | — | cookie/storage/pixel | — | — | — | — |

## Rights and deletion drill

Record the owner, authenticated intake channel, identity-verification method,
search scope across stores/providers, response deadline basis, export format,
secure delivery, correction/restriction path, deletion target, retries/alerts,
and evidence. A row deletion, HTTP success, queue status, or counsel opinion is
not proof that replicas, backups, logs, and providers are deleted.

## Agent and review data stores

Treat the following as possible data-processing stores even when they are not
part of the product database:

| Store | Possible contents | Owner / access | Retention and deletion evidence |
|---|---|---|---|
| Agent prompts, transcripts, and memory | User text, secrets accidentally included, project decisions | Host/provider; project owner | Host policy, redaction, deletion/export evidence |
| Issues, pull requests, and review packets | Intent, diffs, artifacts, vulnerability reports | Repository permissions | Issue retention, private advisory route, deletion evidence |
| CI logs and artifacts | Test output, build metadata, provider/deployment data | CI/provider | Log/artifact expiry and access review |
| Installed skills and provenance | Third-party instructions, scripts, source/revision, permissions | Project owner/host | Trust review, digest, update/rollback record |
| Support exports and analytics | User content, identifiers, usage events | Support/provider | Export minimization, retention, deletion path |

Record the factual role, provider, region, access boundary, and retention path;
do not infer a legal basis or compliance status from this table.

## Review triggers

Review this record when code/schema/config changes a data flow, a provider or
region changes, a new field is collected, a retention job changes, a rights
request/incident occurs, or the operator/jurisdiction changes. Link the current
issue and evidence rather than adding an open-task matrix here.
