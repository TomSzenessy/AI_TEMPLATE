"""Repository kit behind tools/repoctl.py. Standard library only.

Module map. The import graph is acyclic and tools/tests/test_import_graph.py
fails on any cycle, function-local imports included; only the lazy dispatch
imports inside commands.py (kept so `repoctl help` starts fast) are exempt.
Dependencies point toward the leaves (gitinfo, names, helptext import nothing
local):

- leaves and primitives: gitinfo, names, helptext, core, config, surfaces
- capability model: registry (the one loader), checkrun (the check context and
  the one blocking rule), commands and checks (the kit's declarations, gatechecks the gates' rules;
  docs/adr/0002-one-capability-model.md)
- governance: github, docs, skills, structure, issues, ci, launch
- project setup: kitlock (what the kit ships and the lock that records it),
  bootstrap, adopt, kitupdate
- self-healing: docmeta, docsync, hygiene, reachability, coupling, signatures,
  adapters, derive, scaffold, navigate, risk, session, garden, capabilities,
  evals, trial
- product driver: product, uireview (docs/building.md)

Each module owns one concern; tools/repoctl.py only builds its parser from the
@command declarations and dispatches.
"""
