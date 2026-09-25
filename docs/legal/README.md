# Legal and launch gate

This directory is a factual drafting workspace, not legal advice and not a
“GDPR compliant” badge. The applicable law depends on the operator, product,
users, providers, jurisdictions, and actual production configuration.

## Before drafting

1. Identify the operator/controller, legal form, business address, contact,
   jurisdictions, target users, age policy, and every provider/recipient.
2. Inventory real data flows in [`data-inventory.md`](./data-inventory.md).
   Keep its `Project`, `Date`, and `Reviewer` header current; these are launch
   evidence fields, not a compliance claim.
3. Decide which public documents apply: privacy notice, terms, Impressum or
   equivalent provider notice, cookie notice, acceptable-use rules, and
   children/minor language.
4. Mark every statement `pending`, `implemented`, `verified`, or `approved` with
   an owner and evidence. Source code, a default, or a generated page does not
   prove deployment or legal compliance.
5. Have qualified counsel review public terms, lawful bases/roles, transfers,
   retention/deletion, cookies, age/minors, and any regulated-sector or
   consumer obligations before publication.

## Drafting rule

Fill placeholders with verified facts and link the source. Do not invent a
company address, tax ID, legal basis, provider role, retention promise, transfer
mechanism, age threshold, or regulator. Keep the drafts versioned in Git, but
keep approval/status in the issue or launch evidence rather than copying a
project status matrix into every legal file.

## Conditional templates

- [`privacy-notice.template.md`](./privacy-notice.template.md) — structure for
  a factual privacy notice; complete from the inventory and counsel review.
- [`terms.template.md`](./terms.template.md) — neutral drafting scaffold, not
  ready-to-publish contract language.
- [`impressum.template.md`](./impressum.template.md) — provider-information
  scaffold; confirm the applicable jurisdiction and conditional fields.
- [`cookies.template.md`](./cookies.template.md) — browser-storage and consent
  inventory scaffold; a source scan is not runtime evidence.

## Launch evidence record

For a public launch, do not point `launch.legal_document_paths` at these
conditional templates. List only final documents under `docs/legal/`, and add
these factual lines to each listed document (or its versioned review record):

```text
Legal owner: [name/team]
Reviewer: [reviewer]
Date: [YYYY-MM-DD]
```

`launch.legal_review_ref` must point to a versioned local counsel record with
`Counsel review`, `Reviewer`, and `Date` lines. Each
`production_evidence_refs` path must be a local artifact containing
`Evidence type: deployed`, `Observed`, `Reviewer`, and `Date`; a provider or
counsel receipt that cannot be committed should remain an explicit external
`gate:*` issue rather than being represented by a bare `x` path.

The public launch checker also requires a real private security contact and
route in both `project.toml`, `.security/config.json`, and `SECURITY.md`.
These are evidence gates, not legal claims.

Research citations and boundaries live in
[`../research/agentic-repository-baselines.md`](../research/agentic-repository-baselines.md).
