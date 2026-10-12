"""Optional consent-gated semantic code similarity for `make similar --code` (#115).

One owner for the eligible-code inventory, the local vector cache, the
OpenAI-compatible transport, and ranking. Standard library only: no new
catalog, framework, or provider dependency. Off by default
(`[kit].semantic_enabled = false`), and every disabled, unconsented, stale,
or failing semantic path falls back to honest lexical matching with a printed
reason. Similarity never authorizes deleting or rewriting code.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .core import (
    DIRECTORY_ROLES, RepoctlError, code_secret_matches, has_link_component, is_link_like, read_utf8, secret_matches,
)
from .docs import BINARY_SUFFIXES
from .gitinfo import git, is_repository
from .navigate import _jaccard, _tokens

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
# The policy budgets in the short key names `_config` returns (config.py owns the
# semantic_* spelling); scope_digest reads them with exactly these keys. Every finite
# policy bound is included: a change to any of them invalidates stored consent.
BUDGET_KEYS = (
    "batch", "chunk_bytes", "chunk_lines", "max_files",
    "max_chunks", "max_file_bytes", "cache_max_bytes", "top_k",
    "max_requests", "timeout", "retries", "max_response_bytes",
)


class SemanticError(Exception):
    """A refused or failed semantic operation; the message is safe to print (never a key or code)."""


def _config(root: Path) -> dict[str, object]:
    """Every [kit] semantic tunable with its built-in default (config.py is the one owner)."""
    from .config import setting
    return {
        "enabled": bool(setting(root, "semantic_enabled")),
        "endpoint": str(setting(root, "semantic_endpoint")),
        "model": str(setting(root, "semantic_model")),
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
    """Opaque root binding: the resolved local path plus git provenance (origin URL + branch).

    Same origin/branch clones at different physical paths produce different root IDs,
    so consent and cache cannot be reused across clones. The hash is opaque: no remote
    URL, auth userinfo, or filesystem path is logged, stored, or returned in clear.
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
    """Bind provider, model, ignores, and budgets: any policy change invalidates stored consent.

    Content is deliberately absent: a code edit must not re-prompt for consent, it
    only makes the cached vectors stale (index_state detects that by hash). Consent
    is about the policy (where code may go and under which bounds), not each edit.
    """
    canonical = json.dumps({
        "endpoint": config["endpoint"], "model": config["model"],
        "ignores": {"skip_prefixes": config["skip_prefixes"], "code_extensions": config["code_extensions"]},
        "budgets": {key: config[key] for key in BUDGET_KEYS},
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

    This is the single authority for consent validity; confirm_scope and status_lines
    both call it. No second auth logic exists.
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
    """(confirmed, reason). `explicit` is the user's --consent flag; otherwise ask at the terminal.

    A stored consent is accepted only when schema, scope digest, and root binding all
    match. Legacy consent without a root_id is refused: the user must re-confirm.
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


# --- Transport --------------------------------------------------------------------


def _reject_json_constant(value: str) -> float:
    raise ValueError(f"non-finite JSON value {value}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: the Authorization header must not reach another endpoint."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802 - the urllib hook signature
        return None


def _retryable(error: Exception) -> bool:
    if isinstance(error, TimeoutError):
        return True
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or error.code >= 500
    return isinstance(error, urllib.error.URLError)


def validated_embeddings(payload: object, input_count: int) -> list[list[float]]:
    """Strict validation before anything is cached: count, unique indices, dimension, finite, nonzero.

    A partial or malformed response is rejected whole: partial success is not complete.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise SemanticError("embedding response has no data list")
    data = payload["data"]
    if len(data) != input_count:
        raise SemanticError(f"embedding count {len(data)} != input count {input_count}")
    vectors: list[list[float] | None] = [None] * input_count
    dimension = 0
    for item in data:
        if not isinstance(item, dict):
            raise SemanticError("embedding entry is not an object")
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < input_count:
            raise SemanticError(f"embedding index {index!r} is out of range")
        if vectors[index] is not None:
            raise SemanticError(f"duplicate embedding index {index}")
        embedding = item.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise SemanticError(f"embedding {index} is empty or not a list")
        if not dimension:
            dimension = len(embedding)
        elif len(embedding) != dimension:
            raise SemanticError(f"embedding {index} has dimension {len(embedding)}, expected {dimension}")
        clean: list[float] = []
        for value in embedding:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise SemanticError(f"embedding {index} holds a non-finite or non-numeric value")
            clean.append(float(value))
        if not any(clean):
            raise SemanticError(f"embedding {index} is an all-zero vector")
        vectors[index] = clean
    return [vector for vector in vectors if vector is not None]


class OpenAITransport:
    """OpenAI-compatible embeddings POST over the standard library only.

    The endpoint and model are the user's documented choice in [kit]; vendor
    availability, cost, and runtime are unknown and no price or certificate
    claim is made here. Redirects are never followed, so the Authorization
    header cannot leak to another endpoint.
    """

    def __init__(self, endpoint: str, key: str, config: dict) -> None:
        self.url = endpoint.rstrip("/") + "/embeddings"
        self.key = key
        self.config = config
        self.requests = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self.requests += 1
        if self.requests > self.config["max_requests"]:
            raise SemanticError(f"request budget exhausted ({self.config['max_requests']} requests)")
        body = json.dumps({"model": self.config["model"], "input": texts}).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        request.add_header("Authorization", "Bearer " + self.key)
        opener = urllib.request.build_opener(_NoRedirect)
        error: Exception | None = None
        for attempt in range(self.config["retries"] + 1):
            try:
                with opener.open(request, timeout=self.config["timeout"]) as response:
                    raw = response.read(self.config["max_response_bytes"] + 1)
                if len(raw) > self.config["max_response_bytes"]:
                    raise SemanticError("embedding response exceeds the response byte budget")
                try:
                    payload = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
                except ValueError as parse_error:
                    raise SemanticError(f"embedding response is not valid JSON ({parse_error})") from parse_error
                return validated_embeddings(payload, len(texts))
            except SemanticError:
                raise
            except Exception as transport_error:  # noqa: BLE001 - every failure becomes one honest reason
                error = transport_error
                if attempt < self.config["retries"] and _retryable(transport_error):
                    time.sleep(0.1 * (attempt + 1))
                    continue
                break
        detail = "timeout" if isinstance(error, TimeoutError) else type(error).__name__
        raise SemanticError(f"embedding request failed: {detail}")


def configured_transport(root: Path) -> OpenAITransport | None:
    """The transport for the configured endpoint and key, or None when the key is absent.

    Key presence is never consent: a missing key means no outbound, and a present
    key still needs the per-scope confirmation.
    """
    config = _config(root)
    key = os.environ.get(config["api_key_env"], "")
    if not key:
        return None
    return OpenAITransport(config["endpoint"], key, config)


# --- Index build and search -------------------------------------------------------


def _index_inventory(root: Path, config: dict, inventory: dict, transport) -> dict:
    """Embed every eligible chunk in bounded batches; partial success is not complete (nothing is cached).

    Batching is global across all files: chunks from different files share a batch
    when they fit, minimizing outbound requests.
    """
    all_chunks: list[tuple[str, dict]] = []
    for item in inventory["files"]:
        relative, digest = item.split(":", 1)
        try:
            text = read_utf8(root / relative)
        except (OSError, RepoctlError):
            continue
        chunks = chunk_text(text, config)[: config["max_chunks"]]
        for chunk in chunks:
            all_chunks.append((relative, chunk))
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
    for item in inventory["files"]:
        relative, digest = item.split(":", 1)
        try:
            text = read_utf8(root / relative)
        except (OSError, RepoctlError):
            continue
        chunks = chunk_text(text, config)[: config["max_chunks"]]
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
            "counts": {"files": len(files), "chunks": inventory["chunks"], "bytes": inventory["bytes"]}}


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
        transport = configured_transport(root)
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
    snapshot = inventory(root, config)
    if not snapshot["files"]:
        return _lexical(root, query, config), [f"no eligible code files ({snapshot['reason']})"]
    if not config["endpoint"] or not config["model"]:
        return _lexical(root, query, config), ["semantic endpoint/model not configured ([kit].semantic_endpoint, [kit].semantic_model)"]
    if transport is None:
        transport = configured_transport(root)
    if transport is None:
        return _lexical(root, query, config), [f"{config['api_key_env']} is not set; a missing key means no outbound"]
    if secret_matches(query):
        return _lexical(root, query, config), ["the query may contain key material; it was not sent (lexical fallback)"]
    # Index state is evaluated BEFORE consent and BEFORE any outbound call: a missing,
    # stale, or invalid index means there is nothing to search, so the query is never
    # embedded and no consent is prompted. The user is told how to build the index.
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
    key = os.environ.get(config["api_key_env"], "")
    snapshot = inventory(root, config)
    index, state, reason = index_state(root, config, snapshot)
    lines = ["semantic code search: enabled",
             f"  endpoint: {config['endpoint'] or '(not configured)'}",
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
