"""Repository kit behind tools/repoctl.py. Standard library only.

Module map (dependencies point downward; core imports nothing local):

- capability model: registry (the one loader), commands and checks (the kit's
  declarations; docs/adr/0002-one-capability-model.md)
- governance: core, github, docs, skills, structure, issues, ci, launch, bootstrap, adopt
- self-healing: config, docsync, hygiene, adapters, derive, scaffold, navigate, risk,
  session, garden, capabilities, evals, trial, kitupdate
- product driver: product, uireview (docs/building.md)

Each module owns one concern; tools/repoctl.py only builds its parser from the
@command declarations and dispatches.
"""
