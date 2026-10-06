"""Repository kit behind tools/repoctl.py. Standard library only.

Module map (dependencies point downward; core imports nothing local):

- governance: core, github, docs, skills, structure, issues, launch, bootstrap
- self-healing: config, docsync, hygiene, adapters, derive, scaffold, navigate, risk,
  session, garden, capabilities, evals

Each module owns one concern; the CLI in tools/repoctl.py only routes.
"""
