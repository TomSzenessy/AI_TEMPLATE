"""Optional consent-gated semantic code similarity for `make similar --code` (#115).

Owns the eligible-code inventory, local vector cache, and ranking; the
OpenAI-compatible transport lives in `semantic_transport.py`. Standard library
only. Off by default; every disabled/unconsented/stale/failing path falls back to
honest lexical matching with a printed reason. Never authorizes code deletion.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from .core import (
    DIRECTORY_ROLES, RepoctlError, code_secret_matches, ensure_inside_root, has_link_component, is_link_like,
    read_utf8, secret_matches,
)
from .docs import BINARY_SUFFIXES
from .gitinfo import git, is_repository
from .navigate import _jaccard, _tokens
from .semantic_transport import OpenAITransport, SemanticError, _valid_endpoint, validated_embeddings

SCHEMA_VERSION = "semantic-cache-v1"
CONSENT_SCHEMA = "semantic-consent-v1"
INDEX_FILENAME = "semantic-code-cache.json"
CONSENT_FILENAME = "semantic-code-consent.json"
AGENT_DIR = ".agent"
SNIPPET_CHARS = 60

# The same environment and key files the tracked-file hygiene scanner
# (tools/kit/docs.py) blocks: the index never holds them.
KEY_SUFFIXES = frozenset({".key", ".p12", ".pfx", ".pem", ".ppk", ".jks", ".keystore"})
KEY_NAMES = frozenset({
    "id_dsa", "id_ecdsa", "id_ed25519", "id_rsa", ".netrc", ".npmrc", ".pypirc", ".git-credentials",
})
CODE_NAMES = frozenset({"Dockerfile", "Makefile", "GNUmakefile", "CMakeLists.txt", "Rakefile", "Gemfile"})
SKIP_PREFIXES = (".claude/", ".agent/", ".codex/", ".cursor/", ".gemini/", ".github/", ".githooks/", ".security/", ".review/")
SKIP_NAMES = frozenset({".mcp.json", ".DS_Store", ".gitignore", ".gitattributes", ".editorconfig"})
# Every directory the kit already treats as ignored, generated, or infrastructure
# (tools/kit/core.py DIRECTORY_ROLES): product code is what remains.
SKIP_DIRS = frozenset(DIRECTORY_ROLES)
# Every finite [kit] semantic_* budget (config.py owns the spelling); a change to any invalidates stored consent.
BUDGET_KEYS = (
    "batch", "chunk_bytes", "chunk_lines", "max_files",
    "max_chunks", "max_file_bytes", "cache_max_bytes", "top_k",
    "max_requests", "timeout", "retries", "max_response_bytes",
)


# --- Safe environment value resolver (plain data, never executed) --------------
# Process env by presence overrides the private root .env; the key is never logged or stored.

# Strict NAME ASCII env grammar: letter or underscore, then letters/digits/underscores.
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# Config values may reference an environment variable with the explicit env: prefix.
_ENV_REF_PREFIX = "env:"
# The root .env file is read at most this many bytes (finite bound).
_ENV_MAX_BYTES = 64 * 1024
# Placeholder-looking values are not ready (never executed, never sent).
_PLACEHOLDER_RE = re.compile(
    r"^[<\[(].*[>\])]$"  # <...>, [...], (...)
    r"|^(?:your|my|the)[-_ ]"  # your-*, my-*, the-*
    r"|^(?:changeme|change[-_ ]?me|todo|fixme|xxx+|example|placeholder|replace)",
    re.IGNORECASE,
)
# Dynamic-shell-looking values are never executed.
_DYNAMIC_SHELL_RE = re.compile(r"\$\(|\$\{|`|\$[A-Za-z_]")


def _env_name(name: str) -> str:
    """Validate a strict ASCII env name; the error never includes the value."""
    if not _ENV_NAME_RE.fullmatch(name):
        raise SemanticError("invalid environment variable name in [kit] semantic configuration")
    return name


def _parse_env_value(value: str) -> str:
    """Parse a .env value: strip; matching quotes; inline # comments (literal in
    quotes). An unmatched quote is left for `_is_not_ready` to refuse. Plain data only.
    """
    value = value.strip()
    if value[:1] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        if end == -1:
            return value  # unmatched quote: not ready
        return value[1:end]
    hash_pos = value.find("#")
    if hash_pos != -1:
        value = value[:hash_pos].rstrip()
    return value


def _read_dotenv(root: Path, names: frozenset[str]) -> dict[str, str]:
    """Read only the requested names from the root's private .env (regular file
    inside root, <=64 KiB). Plain data, never executed. Unrelated names ignored;
    a name bound twice is ambiguous. No raw value in any error.
    """
    try:
        path = ensure_inside_root(root, root / ".env", ".env file")
    except RepoctlError:
        return {}  # alias/brokenlink: rejected before read
    try:
        info = path.stat()
    except FileNotFoundError:
        return {}
    if not stat.S_ISREG(info.st_mode) or info.st_size > _ENV_MAX_BYTES:
        return {}  # nonregular or too large: rejected before read
    try:
        with path.open("rb") as handle:
            raw = handle.read(_ENV_MAX_BYTES + 1)
    except OSError:
        return {}
    if len(raw) > _ENV_MAX_BYTES:
        return {}  # grew past the bound: rejected after the bounded read
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {}
    found: dict[str, str] = {}
    ambiguous: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if key not in names:
            continue  # ignore unrelated names; never parse all secrets
        if key in ambiguous:
            continue
        if key in found:
            ambiguous.add(key)
            del found[key]
            continue
        found[key] = _parse_env_value(value)
    return found


def _resolve_env_value(root: Path, value: str) -> str:
    """Resolve a [kit] semantic value: a literal, or an explicit env:NAME reference.
    Process env by presence (incl. blank) overrides the root .env; a missing binding is "".
    """
    if not value.startswith(_ENV_REF_PREFIX):
        return value
    name = _env_name(value[len(_ENV_REF_PREFIX):])
    if name in os.environ:
        return os.environ[name]
    return _read_dotenv(root, frozenset({name})).get(name, "")


def _is_not_ready(value: str) -> bool:
    """A missing, placeholder, dynamic-shell, or unmatched-quote binding is not ready."""
    if not value:
        return True
    if value[:1] in ("'", '"') and value.find(value[0], 1) == -1:
        return True  # unmatched quote: refuse rather than send a malformed value
    return bool(_PLACEHOLDER_RE.search(value) or _DYNAMIC_SHELL_RE.search(value))


def _config(root: Path) -> dict[str, object]:
    """Every [kit] semantic tunable with its built-in default (config.py is the one owner).

    endpoint/model accept a literal or an explicit env:NAME reference; the
    convenient disabled defaults reference EMBEDDINGS_ENDPOINT/EMBEDDINGS_MODEL.
    """
    from .config import setting
    return {
        "enabled": bool(setting(root, "semantic_enabled")),
        "endpoint": _resolve_env_value(root, str(setting(root, "semantic_endpoint"))),
        "model": _resolve_env_value(root, str(setting(root, "semantic_model"))),
        "api_key_env": str(setting(root, "semantic_api_key_env")),
        "timeout": float(setting(root, "semantic_timeout_seconds")),
        "retries": int(setting(root, "semantic_retries")),
        "max_requests": int(setting(root, "semantic_max_requests")),
        "batch": int(setting(root, "semantic_batch_chunks")),
        "chunk_bytes": int(setting(root, "semantic_chunk_bytes")),
        "chunk_lines": int(setting(root, "semantic_chunk_lines")),
        "max_files": int(setting(root, "semantic_max_files")),
        "max_chunks": int(setting(root, "semantic_max_chunks")),
        "max_file_bytes": int(setting(root, "semantic_max_file_bytes")),
        "cache_max_bytes": int(setting(root, "semantic_cache_max_bytes")),
        "max_response_bytes": int(setting(root, "semantic_max_response_bytes")),
        "top_k": int(setting(root, "semantic_top_k")),
        "code_extensions": list(setting(root, "semantic_code_extensions")),
        "skip_prefixes": list(setting(root, "semantic_skip_prefixes")),
        "schema": str(setting(root, "semantic_schema_version")),
    }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _root_id(root: Path) -> str:
    """Opaque root binding: resolved path + git provenance (origin URL + branch).
    Distinct physical clones get distinct IDs; the hash leaks no URL, userinfo, or path.
    """
    resolved = str(root.resolve())
    remote = git(root, "remote", "get-url", "origin")
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    provenance = f"{remote.strip()}:{branch.strip()}" if remote and branch else "local"
    return "root:" + _sha256(f"{resolved}\n{provenance}")


# --- Eligible code inventory ---------------------------------------------------


def _excluded(root: Path, relative: str, path: Path, config: dict) -> str | None:
    """Why a tracked file is not eligible code, or None when it is."""
    parts = relative.split("/")
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return "infrastructure or generated directory"
    if relative.startswith(tuple(config["skip_prefixes"])):
        return "skipped prefix"
    name = parts[-1].lower()
    if name in SKIP_NAMES or name.startswith(".env") or name in KEY_NAMES or Path(name).suffix in KEY_SUFFIXES:
        return "environment or key file"
    if Path(name).suffix in BINARY_SUFFIXES:
        return "binary"
    if Path(name).suffix not in frozenset(config["code_extensions"]) and name not in CODE_NAMES:
        return "not textual code"
    if is_link_like(path) or has_link_component(root, path):
        return "symlink"
    return None


def _eligible_files(root: Path, config: dict) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """(relative, text) for every eligible tracked code file within the file/chunk budgets, plus skip counts."""
    listed = git(root, "ls-files", "--cached", "-z")
    candidates = [item for item in (listed or "").split("\0") if item]
    eligible: list[tuple[str, str]] = []
    skipped: dict[str, int] = {}
    chunks = 0
    for relative in candidates:
        if len(eligible) >= config["max_files"]:
            skipped["file budget reached"] = skipped.get("file budget reached", 0) + 1
            continue
        path = root / relative
        reason = _excluded(root, relative, path, config)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        try:
            if path.stat().st_size > config["max_file_bytes"]:
                skipped["over file byte budget"] = skipped.get("over file byte budget", 0) + 1
                continue
            text = read_utf8(path)
        except (OSError, RepoctlError):
            skipped["unreadable or not UTF-8"] = skipped.get("unreadable or not UTF-8", 0) + 1
            continue
        if code_secret_matches(text):
            skipped["flagged by the hygiene scanner"] = skipped.get("flagged by the hygiene scanner", 0) + 1
            continue
        file_chunks = chunk_text(text, config)
        if chunks + len(file_chunks) > config["max_chunks"]:
            file_chunks = file_chunks[: config["max_chunks"] - chunks]
        if not file_chunks:
            continue
        chunks += len(file_chunks)
        eligible.append((relative, text))
    return eligible, skipped


def inventory(root: Path, config: dict) -> dict:
    """Eligible git-tracked textual code within every budget.

    Returns {"files": ["path:sha256", ...] (sorted), "chunks": n, "bytes": n,
    "skipped": {reason: n}, "reason": str (empty when files were found)}.
    """
    if not is_repository(root):
        return {"files": [], "chunks": 0, "bytes": 0, "skipped": {}, "reason": "not a git repository"}
    listed = git(root, "ls-files", "--cached", "-z")
    if listed is None:
        return {"files": [], "chunks": 0, "bytes": 0, "skipped": {}, "reason": "git unavailable"}
    candidates = [item for item in listed.split("\0") if item]
    result = {"files": [], "chunks": 0, "bytes": 0, "skipped": {}}
    if candidates:
        eligible, skipped = _eligible_files(root, config)
        result["skipped"] = skipped
        result["files"] = sorted(f"{relative}:{_sha256(text)}" for relative, text in eligible)
        result["chunks"] = sum(len(chunk_text(text, config)) for _, text in eligible)
        result["bytes"] = sum(len(text.encode("utf-8")) for _, text in eligible)
    result["reason"] = "" if result["files"] else (
        "no tracked files (new repository)" if not candidates else "no textual code in scope"
    )
    return result


def chunk_text(text: str, config: dict) -> list[dict]:
    """Bounded UTF-8-safe line chunks: line boundaries only, byte and line budgets enforced."""
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line.encode("utf-8")))
    chunks: list[dict] = []
    start = 0
    while start < len(lines):
        end = start
        while (end < len(lines) and end - start < config["chunk_lines"]
               and offsets[end + 1] - offsets[start] <= config["chunk_bytes"]):
            end += 1
        if end == start:
            end = start + 1  # one oversized line is still a bounded chunk
        body = "".join(lines[start:end])
        chunks.append({"start_line": start + 1, "end_line": end, "byte_start": offsets[start],
                       "byte_end": offsets[end], "text": body, "sha256": _sha256(body)})
        start = end
    return chunks


# --- Consent --------------------------------------------------------------------


def scope_digest(config: dict, inventory: dict) -> str:
    """Bind provider, model, ignores, budgets, and the eligible inventory.

    Carries sorted eligible PATHS, file count, and chunk count — never content
    hashes, byte counts, or code text. Any path-set or chunk-count change requires
    fresh consent; a code edit preserving both does NOT re-prompt (index_state
    detects staleness by content hash instead). This is deliberate (#130): consent
    means "these files may be indexed", not "this exact content"; every send is an
    explicit `make similar CODE_INDEX=1` run that prints the scope first.
    """
    canonical = json.dumps({
        "endpoint": config["endpoint"], "model": config["model"],
        "ignores": {"skip_prefixes": config["skip_prefixes"], "code_extensions": config["code_extensions"]},
        "budgets": {key: config[key] for key in BUDGET_KEYS},
        "scope": {
            "paths": sorted(item.rsplit(":", 1)[0] for item in inventory["files"]),
            "files": len(inventory["files"]),
            "chunks": inventory["chunks"],
        },
    }, sort_keys=True)
    return "sha256:" + _sha256(canonical)


def load_consent(root: Path) -> dict | None:
    try:
        record = json.loads((root / AGENT_DIR / CONSENT_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def save_consent(root: Path, record: dict) -> None:
    path = root / AGENT_DIR / CONSENT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _consent_matches(root: Path, config: dict, inventory: dict) -> bool:
    """The one consent checker: schema, scope digest, and root binding must all match.
    confirm_scope and status_lines both call it; no second auth logic exists.
    """
    record = load_consent(root)
    if not record or record.get("schema") != CONSENT_SCHEMA:
        return False
    if record.get("scope_digest") != scope_digest(config, inventory):
        return False
    if record.get("root_id") != _root_id(root):
        return False
    return True


def confirm_scope(root: Path, config: dict, inventory: dict, *, explicit: bool) -> tuple[bool, str]:
    """(confirmed, reason). `explicit` is the --consent flag; otherwise prompt.
    A stored consent matches only on schema + scope digest + root binding; legacy consent is refused.
    """
    digest = scope_digest(config, inventory)
    if _consent_matches(root, config, inventory):
        return True, ""
    if not explicit:
        print("Semantic code search (#115): outbound code transfer needs explicit consent.")
        print(f"  endpoint: {config['endpoint']}")
        print(f"  model: {config['model']}")
        print(f"  eligible files: {len(inventory['files'])} ({inventory['chunks']} chunks, {inventory['bytes']} bytes, budgets enforced)")
        print(f"  scope digest: {digest[:18]}… (any changed policy invalidates it)")
        try:
            answer = input("Send eligible code to this endpoint? [y/N] ").strip().lower()
        except EOFError:
            return False, "no consent: no confirmation on stdin; nothing was sent (lexical fallback)"
        if answer not in {"y", "yes"}:
            return False, "no consent: nothing was sent (lexical fallback)"
    save_consent(root, {"schema": CONSENT_SCHEMA, "root_id": _root_id(root), "scope_digest": digest,
                        "endpoint": config["endpoint"], "model": config["model"],
                        "files": len(inventory["files"]), "chunks": inventory["chunks"],
                        "bytes": inventory["bytes"], "confirmed_at": _now()})
    return True, ""


# --- Cache ----------------------------------------------------------------------


def save_index(root: Path, config: dict, index: dict) -> str | None:
    """Atomically write the cache, keeping the last valid one on any failure.

    Returns None when written, else an honest reason (for example the cache byte budget).
    """
    text = json.dumps(index, separators=(",", ":"), sort_keys=True) + "\n"
    if len(text.encode("utf-8")) > config["cache_max_bytes"]:
        return (f"index is {len(text.encode('utf-8'))} bytes, over the {config['cache_max_bytes']}-byte cache budget; "
                "last valid cache kept")
    path = root / AGENT_DIR / INDEX_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        return "the cache could not be written; last valid cache kept"
    return None


def index_state(root: Path, config: dict, inventory: dict) -> tuple[dict | None, str, str]:
    """(index, state, reason) with state in missing|invalid|stale|valid; the index is returned only when valid."""
    path = root / AGENT_DIR / INDEX_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "missing", "index missing (run: make similar --code-index)"
    if not isinstance(raw, dict):
        return None, "invalid", "index unreadable"
    for ok, reason in (
        (raw.get("schema_version") == config["schema"], "schema version changed"),
        (raw.get("root_id") == _root_id(root), "repository root changed"),
        (raw.get("model") == config["model"], "model changed"),
        (raw.get("endpoint") == config["endpoint"], "endpoint changed"),
    ):
        if not ok:
            return None, "stale", reason
    entries = raw.get("files")
    if not isinstance(entries, list):
        return None, "invalid", "index malformed"
    cached: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            return None, "invalid", "index malformed"
        cached[entry["path"]] = entry
    try:
        current = dict(item.split(":", 1) for item in inventory["files"])
    except ValueError:
        return None, "invalid", "index malformed"
    if set(cached) != set(current):
        return None, "stale", "eligible file set changed since indexing"
    for relative, digest in current.items():
        entry = cached.get(relative)
        if entry is None or entry.get("sha256") != digest:
            return None, "stale", "code changed since indexing"
    if raw.get("scope_digest") != scope_digest(config, inventory):
        return None, "stale", "budget or ignore policy changed since indexing"
    return raw, "valid", ""


def configured_transport(root: Path, config: dict | None = None) -> OpenAITransport | None:
    """The transport for the configured endpoint and key, or None when the key is absent.

    Key presence is never consent. `config` is the resolved [kit] snapshot: the
    transport uses exactly the approved model/endpoint — no re-read, no tuple A→B.
    The key comes from the safe env resolver and is never added to cfg, consent
    records, or caches; the approved endpoint/model tuple is never re-resolved.
    """
    if config is None:
        config = _config(root)
    endpoint = config["endpoint"]
    model = config["model"]
    if not endpoint or not model or _is_not_ready(endpoint) or _is_not_ready(model):
        return None
    _valid_endpoint(endpoint)
    key_env = config["api_key_env"]
    try:
        _env_name(key_env)
    except SemanticError:
        return None  # an unsafe key-env name is never looked up, never sent
    key = os.environ.get(key_env, "")
    if not key:
        key = _read_dotenv(root, frozenset({key_env})).get(key_env, "")
    if not key or _is_not_ready(key):
        return None
    return OpenAITransport(endpoint, key, config)


# --- Index build and search -------------------------------------------------------


def _index_inventory(root: Path, config: dict, inventory: dict, transport) -> dict:
    """Embed every eligible chunk in bounded batches; partial success caches nothing.
    Batching is global across files to minimize outbound requests.
    """
    all_chunks: list[tuple[str, dict]] = []
    per_file: list[tuple[str, str, list[dict]]] = []
    for item in inventory["files"]:
        relative, digest = item.split(":", 1)
        try:
            text = read_utf8(root / relative)  # the one read: chunked, embedded, and hashed from this text
        except (OSError, RepoctlError):
            continue
        if _sha256(text) != digest:
            continue  # edited since the inventory was confirmed: skip as stale, never record a mismatched hash
        chunks = chunk_text(text, config)[: config["max_chunks"]]
        per_file.append((relative, digest, chunks))
        all_chunks.extend((relative, chunk) for chunk in chunks)
    batches = math.ceil(len(all_chunks) / config["batch"]) if all_chunks else 0
    if batches > config["max_requests"]:
        raise SemanticError(
            f"request budget too small for {len(all_chunks)} chunks (batch {config['batch']}, "
            f"max {config['max_requests']} requests); raise [kit].semantic_batch_chunks or semantic_max_requests"
        )
    all_vectors: list[list[float]] = []
    for start in range(0, len(all_chunks), config["batch"]):
        batch = all_chunks[start : start + config["batch"]]
        all_vectors += transport.embed([chunk["text"] for _, chunk in batch])
    files: list[dict] = []
    vector_index = 0
    for relative, digest, chunks in per_file:
        vectors = all_vectors[vector_index : vector_index + len(chunks)]
        vector_index += len(chunks)
        files.append({
            "path": relative, "sha256": digest,
            "chunks": [{key: chunk[key] for key in ("start_line", "end_line", "byte_start", "byte_end", "sha256")}
                       | {"vector": vector} for chunk, vector in zip(chunks, vectors)],
        })
    return {"schema_version": config["schema"], "root_id": _root_id(root), "model": config["model"],
            "endpoint": config["endpoint"], "scope_digest": scope_digest(config, inventory), "created_at": _now(),
            "files": files,
            "counts": {"files": len(files), "chunks": len(all_chunks), "bytes": inventory["bytes"]}}


def build_index(root: Path, *, transport=None, consent: bool = False) -> list[str]:
    """The explicit index operation (make similar --code-index); every refusal is an honest line."""
    config = _config(root)
    if not config["enabled"]:
        return ["semantic code search is disabled ([kit].semantic_enabled is true to enable); index not built"]
    snapshot = inventory(root, config)
    if not snapshot["files"]:
        return [f"no eligible code files ({snapshot['reason']}); index not built"]
    if not config["endpoint"] or not config["model"]:
        return ["semantic endpoint/model not configured ([kit].semantic_endpoint, [kit].semantic_model); index not built"]
    if transport is None:
        try:
            transport = configured_transport(root, config)
        except SemanticError as error:
            return [f"{error}; index not built"]
    if transport is None:
        return [f"{config['api_key_env']} is not set; index not built (a key is never consent by itself)"]
    confirmed, reason = confirm_scope(root, config, snapshot, explicit=consent)
    if not confirmed:
        return [reason or "no consent; index not built"]
    try:
        index = _index_inventory(root, config, snapshot, transport)
    except SemanticError as error:
        return [f"index build failed: {error}"]
    skip = save_index(root, config, index)
    if skip:
        return [f"index computed but not cached: {skip}"]
    counts = index["counts"]
    return [f"index built: {counts['files']} files, {counts['chunks']} chunks, {counts['bytes']} bytes "
            f"(model {config['model']}, endpoint {config['endpoint']})"]


def _snippet(root: Path, relative: str, start_line: int, end_line: int) -> str:
    """A short local preview line for a chunk (never outbound)."""
    try:
        lines = read_utf8(root / relative).splitlines()
    except (OSError, RepoctlError):
        return ""
    for number in range(start_line, min(end_line or start_line, len(lines)) + 1):
        text = " ".join(lines[number - 1].split())
        if text:
            return text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 3] + "…"
    return ""


def _norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _rank(root: Path, index: dict, query_vector: list[float], top_k: int) -> list[tuple[float, str, str]]:
    query_norm = _norm(query_vector)
    scored: list[tuple[float, str, str]] = []
    for entry in index["files"]:
        for chunk in entry["chunks"]:
            vector = chunk.get("vector")
            if not isinstance(vector, list) or not vector:
                continue
            denominator = query_norm * _norm(vector)
            score = sum(a * b for a, b in zip(query_vector, vector)) / denominator if denominator else 0.0
            if score > 0:
                path = entry["path"]
                label = f"code:{path}:{chunk['start_line']}-{chunk['end_line']}"
                scored.append((score, label, _snippet(root, path, chunk["start_line"], chunk["end_line"])))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[:top_k]


def _lexical(root: Path, query: str, config: dict) -> list[tuple[float, str, str]]:
    """Lexical code matching by the navigate.skill_overlap convention (tokens + Jaccard)."""
    tokens = _tokens(query)
    if not tokens:
        return []
    scored: list[tuple[float, dict]] = []
    eligible, _ = _eligible_files(root, config)
    for relative, text in eligible:
        for chunk in chunk_text(text, config):
            score = _jaccard(tokens, _tokens(chunk["text"]))
            if score > 0:
                scored.append((score, {"path": relative, "start_line": chunk["start_line"],
                                       "end_line": chunk["end_line"]}))
    scored.sort(key=lambda item: (-item[0], item[1]["path"], item[1]["start_line"]))
    return [(score, f"code:{chunk['path']}:{chunk['start_line']}-{chunk['end_line']}",
             _snippet(root, chunk["path"], chunk["start_line"], chunk["end_line"]))
            for score, chunk in scored[: config["top_k"]]]


def code_matches(root: Path, query: str, *, transport=None, consent: bool = False) -> tuple[list[tuple[float, str, str]], list[str]]:
    """Ranked code matches with honest fallback reasons (make similar Q=... --code)."""
    config = _config(root)
    if not config["enabled"]:
        return _lexical(root, query, config), ["semantic code search is disabled ([kit].semantic_enabled is false)"]
    if not query.strip():
        return _lexical(root, query, config), ["no query; no outbound (lexical fallback)"]
    snapshot = inventory(root, config)
    if not snapshot["files"]:
        return _lexical(root, query, config), [f"no eligible code files ({snapshot['reason']})"]
    if not config["endpoint"] or not config["model"]:
        return _lexical(root, query, config), ["semantic endpoint/model not configured ([kit].semantic_endpoint, [kit].semantic_model)"]
    if transport is None:
        try:
            transport = configured_transport(root, config)
        except SemanticError as error:
            return _lexical(root, query, config), [f"{error} (lexical fallback)"]
    if transport is None:
        return _lexical(root, query, config), [f"{config['api_key_env']} is not set; a missing key means no outbound"]
    if secret_matches(query):
        return _lexical(root, query, config), ["the query may contain key material; it was not sent (lexical fallback)"]
    # Index state is checked BEFORE consent and any outbound call: a missing/stale/
    # invalid index means nothing to search, so the query is never embedded and no
    # consent is prompted.
    index, state, state_reason = index_state(root, config, snapshot)
    if index is None:
        if state == "missing":
            return _lexical(root, query, config), [state_reason, "run: make similar Q=... --code-index to build it (explicit, consent-gated)"]
        return _lexical(root, query, config), [state_reason]
    # A valid index: confirm consent before embedding the query (one outbound call).
    confirmed, reason = confirm_scope(root, config, snapshot, explicit=consent)
    if not confirmed:
        return _lexical(root, query, config), [reason]
    try:
        query_vector = transport.embed([query])[0]
    except SemanticError as error:
        return _lexical(root, query, config), [str(error)]
    return _rank(root, index, query_vector, config["top_k"]), []


def status_lines(root: Path) -> list[str]:
    """Local index and consent status for make similar --code-status; never outbound."""
    config = _config(root)
    if not config["enabled"]:
        return ["semantic code search: disabled ([kit].semantic_enabled is true to enable)"]
    key_env = config["api_key_env"]
    try:
        _env_name(key_env)
        key = os.environ.get(key_env, "") or _read_dotenv(root, frozenset({key_env})).get(key_env, "")
    except SemanticError:
        key = ""
    endpoint = config["endpoint"] or "(not configured)"
    if config["endpoint"] and not _is_not_ready(config["endpoint"]):
        try:
            _valid_endpoint(config["endpoint"])
        except SemanticError as error:
            endpoint = f"(invalid: {error})"  # never echo a URL that may carry credentials
    snapshot = inventory(root, config)
    index, state, reason = index_state(root, config, snapshot)
    lines = ["semantic code search: enabled",
             f"  endpoint: {endpoint}",
             f"  model: {config['model'] or '(not configured)'}",
             f"  key: {config['api_key_env']} {'set' if key else 'not set'}"]
    if snapshot["files"]:
        lines.append(f"  eligible: {len(snapshot['files'])} files, {snapshot['chunks']} chunks, {snapshot['bytes']} bytes")
    else:
        lines.append(f"  eligible: none ({snapshot['reason']})")
    lines.append(f"  index: {state}" + (f" ({reason})" if reason else ""))
    if _consent_matches(root, config, snapshot):
        record = load_consent(root)
        lines.append(f"  consent: confirmed {record.get('confirmed_at', '?')} (scope {str(record.get('scope_digest'))[:12]}…)")
    else:
        lines.append("  consent: none for the current scope (a changed policy or root invalidates a stored confirmation)")
    return lines
