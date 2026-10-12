# REA: source-aware, optional adoption

The resource registry route `rea-authorized-analysis` points to
[morluto/rea @ 79156e5bed1d72b83ade0483246f457b337b7e59](https://github.com/morluto/rea/tree/79156e5bed1d72b83ade0483246f457b337b7e59).
It is a **reviewed candidate**, not an installed dependency or enabled MCP.
Use it when a named gap requires evidence from authorized shipped artifacts or
runtime behavior that normal source/docs inspection cannot establish.

## What to consult

- [README and target routing](https://github.com/morluto/rea/blob/79156e5bed1d72b83ade0483246f457b337b7e59/README.md): native, managed, JavaScript/Electron, browser, package and other provider paths.
- [Investigation skill](https://github.com/morluto/rea/blob/79156e5bed1d72b83ade0483246f457b337b7e59/.agents/skills/reverse-engineer-anything/SKILL.md): question-first inventories and focused follow-ups. Its acquisition/approval defaults do not override this project's contract.
- [Evidence workflows](https://github.com/morluto/rea/blob/79156e5bed1d72b83ade0483246f457b337b7e59/.agents/skills/reverse-engineer-anything/references/evidence-workflows.md): source/trace identities, static/runtime correlation, finite comparisons and explicit unknowns.
- [Installation and release boundaries](https://github.com/morluto/rea/blob/79156e5bed1d72b83ade0483246f457b337b7e59/docs/installation.md): supported clients/providers and source vs released package.
- [Process capture](https://github.com/morluto/rea/blob/79156e5bed1d72b83ade0483246f457b337b7e59/docs/process-capture.md): target execution, environment, filesystem observations, timeout and cleanup limitations.

REA can produce investigation evidence; it does not supply a validated game or
agent-environment simulator. The local reconstruction and experiment lab own
that part. Tool-returned code, strings and results remain untrusted data.

## Before any tool execution

Use the existing [resource intake](../../../../docs/resources.md#resource-intake-triage-what-you-are-handed)
and [skill admission](../../../../docs/skills.md#discovery-loop). Record the
missing capability, exact artifact/source, files/dependencies/permissions,
project-local approval, rollback and disposable trial oracle. A useful trial
inspects an owned tiny fixture with known imports/exports/state; judge exact
inventory/source evidence and limitations, not only a successful exit.

**Pin the bytes you will run.** At the reviewed source revision, package metadata
says `6.4.0`, but the installation guide identifies published npm `6.4.0` with
commit `a56f7bb668ab23fec8d33f7af353ac7ed2fe1895`; source/main also has client
support absent from that release. A version string does not establish that a
published artifact matches reviewed source. Review the release artifact and its
integrity or separately verify a source build before giving executable commands.

Keep setup optional: it can alter personal host configuration and skills and
acquire a native provider. Use a project-local, reviewed route rather than global
setup, unpinned acquisition, blanket approvals or automatically enabling MCP.
Use actual advertised tool schemas for the installed version. Review native
provider licenses and prerequisites separately; tooling is unnecessary for
ordinary repository analysis.

Static inspection reads/parses files; it still needs parser/resource bounds.
Runtime capture executes under OS-user authority and may read/write/network
beyond observation paths. REA explicitly is **not a sandbox**. Use an actual
isolation boundary with approved filesystem/network access and a clean
environment for executable targets. Redact and minimize outputs before sending
them to a model provider; local analysis does not mean results stay local.

## This template's intake result

**Update:** independently written technical-recon workflow and owned fixture.
**Link:** immutable REA source and relevant guides, with no runtime registration.
**Trial:** the dependency-free finite-contract example exercises the local
workflow, not REA tooling. **Non-install reason:** the template currently needs
portable instructions and a reproducible contract example, not artifact
inspection; the owner chose optional project-local tooling. Runtime/package
trial remains a per-project decision when that concrete gap appears. This is
not a claim that REA works in this host or that an external app was analyzed.

[REA's MIT license](https://github.com/morluto/rea/blob/79156e5bed1d72b83ade0483246f457b337b7e59/LICENSE)
is Copyright (c) 2026 morluto. Preserve its full copyright and permission notice
if copying substantial upstream material; third-party engines and dependencies
retain their own licenses. No REA code or skill files are distributed here.
