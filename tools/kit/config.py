"""Kit tunables: project.toml `[kit]` overrides, built-in defaults otherwise.

Policy a project may reasonably change lives in the manifest, not in code.
Omitting a key keeps the default, so a minimal manifest still works.
"""

from __future__ import annotations

from pathlib import Path

from .core import RepoctlError, load_project
from .names import ERROR_LOG, STACK_DECISION

DEFAULTS: dict[str, object] = {
    # Sections of the generated docs index, in display order: key = title.
    "doc_groups": {
        "operate": "Start and operate",
        "design": "Design and engineering",
        "launch": "Product, privacy, and launch",
        "extend": "Extensibility and evidence",
    },
    # Policy documents that need no covers binding (no garden note for them).
    "unbound_docs_ok": [
        "docs/legal/**", "docs/research/**", "docs/incidents/**", "docs/handoffs/**", "docs/adr/**",
        "docs/README.md", ERROR_LOG, STACK_DECISION, "docs/audit.md",
        "docs/engineering.md", "docs/operations.md", "docs/privacy.md", "docs/verification.md",
    ],
    "overlap_limit": 0.30,
    "deprecation_warning_days": 30,
    "skill_review_days": 365,
    # Project kinds whose product has a user interface (they need docs/design.md).
    "ui_kinds": ["web", "app", "site", "pwa", "mobile", "ios", "android", "desktop", "game"],
    # UI kinds served from a local URL, so make ui-review can screenshot them; native
    # kinds (ios, android, desktop, game) are reviewed in a simulator instead.
    "preview_kinds": ["web", "app", "site", "pwa"],
    # "new" for a project started from scratch, "adopt" for one that already had a
    # product when the kit arrived. An adopted project scopes a feature delta from its
    # own code, so `make next` does not send it to competitor research (#58).
    "project_mode": "new",
    # Pinned Playwright for make ui-review (1.57 still supports Node 18).
    "playwright_version": "1.63.0",
    # Model for headless eval runs on hosts that accept one; cheap by default.
    "eval_model": "haiku",
}


def project_setting(project: dict[str, object], key: str) -> object:
    kit = project.get("kit", {})
    if not isinstance(kit, dict):
        raise RepoctlError("[kit] must be a table")
    value = kit.get(key, DEFAULTS[key])
    default = DEFAULTS[key]
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)  # bool is an int in Python
    if type(value) is not type(default) and not (is_number and isinstance(default, (int, float))):
        raise RepoctlError(f"[kit].{key} must be a {type(DEFAULTS[key]).__name__}")
    return value


def setting(root: Path, key: str) -> object:
    return project_setting(load_project(root), key)
