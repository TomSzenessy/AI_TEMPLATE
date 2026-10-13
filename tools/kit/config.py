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
    # Optional consent-gated semantic code similarity for `make similar --code` (#115).
    # Off by default; standard library only; every disabled/unconsented/stale/failing
    # path falls back to honest lexical matching. Similarity never deletes code.
    # endpoint/model accept a literal or an explicit `env:NAME` reference; the
    # convenient disabled defaults reference EMBEDDINGS_ENDPOINT/EMBEDDINGS_MODEL.
    "semantic_enabled": False,
    "semantic_endpoint": "env:EMBEDDINGS_ENDPOINT",
    "semantic_model": "env:EMBEDDINGS_MODEL",
    "semantic_api_key_env": "EMBEDDINGS_API_KEY",
    "semantic_timeout_seconds": 10.0,
    "semantic_retries": 1,
    "semantic_max_requests": 8,
    "semantic_batch_chunks": 64,
    "semantic_chunk_bytes": 4096,
    "semantic_chunk_lines": 200,
    "semantic_max_files": 200,
    "semantic_max_chunks": 2000,
    "semantic_max_file_bytes": 262144,
    "semantic_cache_max_bytes": 8388608,
    "semantic_max_response_bytes": 8388608,
    "semantic_top_k": 5,
    "semantic_code_extensions": [
        ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss", ".html", ".htm",
        ".sh", ".bash", ".zsh", ".rb", ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h",
        ".cpp", ".cc", ".cxx", ".hpp", ".cs", ".php", ".sql", ".yaml", ".yml", ".toml", ".xml",
        ".vue", ".svelte", ".lua", ".pl", ".pm", ".r", ".scala", ".clj", ".ex", ".exs", ".erl",
        ".hrl", ".ml", ".mli", ".fs", ".fsx", ".dart", ".jl", ".nim", ".zig", ".v", ".sv", ".vhd",
        ".proto", ".graphql", ".gql", ".tf", ".hcl", ".mk", ".cmake", ".gradle",
    ],
    "semantic_skip_prefixes": [
        ".claude/", ".agent/", ".agents/", ".codex/", ".cursor/", ".gemini/", ".github/", ".githooks/",
        ".security/", ".review/",
    ],
    "semantic_schema_version": "semantic-cache-v1",
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
