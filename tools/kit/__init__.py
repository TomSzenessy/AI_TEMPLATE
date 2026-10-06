"""Repository kit behind tools/repoctl.py. Standard library only.

Module map (dependencies point downward; core imports nothing local):

- governance: core, github, docs, skills, structure, issues, launch, bootstrap
- self-healing: docsync, hygiene, adapters, navigate, session, garden, evals

Each module owns one concern; the CLI in tools/repoctl.py only routes.
"""
