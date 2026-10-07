"""File names the kit reads by convention, defined once so a rename is one edit."""

from __future__ import annotations

VISION = "VISION.md"
STACK_DECISION = "docs/STACK-DECISION.md"
DESIGN = "docs/design.md"
ERROR_LOG = "docs/ERROR_LOG.md"
HANDOVER = "HANDOVER.md"

# Agent working records the kit writes (session) and `reachability` knows by name.
CHECKPOINT = ".agent/checkpoint.md"
CRITIC_RECORD = ".agent/critic.md"

# The one list of hook events: `repoctl hook <event>` and its argument choices, the host
# adapter wiring (adapters.py), and the dispatcher (session.py) all use these names.
SESSION_START, PRE_COMPACT, AFTER_EDIT, STOP, COMMIT_MSG = (
    "session-start", "pre-compact", "after-edit", "stop", "commit-msg",
)
