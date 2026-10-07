"""Cheap navigation: a one-screen repository map, `where` lookups, and capability overlap.

These answer "what is here", "where does X live / who owns it / which rule
applies / did it break before", and "does a capability already exist" in one
call, so agents spend context on the task instead of on repeated searches.
"""

from __future__ import annotations

import re
from pathlib import Path

from .core import declared_surfaces, governance_profile, load_project, read_text_file, repository_files
from .docmeta import bindings, owners
from .gitinfo import git, is_repository, path_matches
from .names import ERROR_LOG
from .registry import Registry

SYMBOL = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:pub(?:\([^)]*\))?\s+)?"
    r"(?:def|class|function|interface|type|struct|enum|trait|impl|fn|func|const|let|var|module)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)
HEADING = re.compile(r"^#{1,4}\s+(.+)$")
MEMORY_FILES = (ERROR_LOG,)
SKIP_PREFIXES = (".claude/",)
WORD = re.compile(r"[a-z0-9]+")


def _short(text: str, limit: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def print_map(root: Path, limit: int | None = None) -> None:
    """Print the map; limit caps long sections (the session brief stays small at any scale)."""
    project = load_project(root)
    files = repository_files(root)
    print(f"# Map: {project.get('name')} ({project.get('kind')}, phase={project.get('phase')}, profile={governance_profile(project)})")
    print("\n## Surfaces (project.toml)")
    surfaces = declared_surfaces(project)
    for surface in surfaces[:limit]:
        commands = [" ".join(command) for command in surface.get("verification", [])]
        print(f"- {surface.get('id')} [{surface.get('status', 'active')}] {surface.get('path')} — verify: {_short('; '.join(commands) or 'critic evidence', 90)}")
    if limit is not None and len(surfaces) > limit:
        print(f"- … {len(surfaces) - limit} more (make map)")
    doc_bindings = bindings(root, files)
    if doc_bindings:
        print("\n## Doc ownership (<!-- covers: --> bindings; for one file: make where Q=<path>)")
        items = sorted(doc_bindings.items())
        for doc, patterns in items[:limit]:
            print(f"- {doc} ← {_short(' '.join(patterns), 110)}")
        if limit is not None and len(items) > limit:
            print(f"- … {len(items) - limit} more (make map)")
    registry = Registry(root)
    roles = registry.of("agent")
    if roles:
        print("\n## Delegation roles (.agents/agents/, contract: docs/delegation.md)")
        for role in roles:
            print(f"- {role.name} [{role.fields['access']}, {role.fields['tier']}]: {_short(role.description, 80)}")
    skills = registry.of("skill")
    if skills:
        print("\n## Skills (.agents/skills/)")
        print("- " + ", ".join(skill.name for skill in skills))
    off = sorted(name for name, enabled in registry.pack_state.items() if not enabled)
    if off:
        print(f"\n## Packs switched off (findable with make capabilities): {', '.join(off)}")
    print("\n## Commands")
    print("- make where Q=\"...\" · make done · make new · make similar Q=\"...\" · make risk · make garden · make help")


def _score(terms: list[str], text: str) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def _candidate_lines(root: Path, files: list[str], terms: list[str]):
    """Yield (path, line number, text) for lines containing any term.

    Uses `git grep` (fast at very large scale) and falls back to a Python scan
    outside git. Files over 400 KB and binaries are skipped either way.
    """
    if is_repository(root):
        arguments = ["grep", "-n", "-I", "-i", "-z", "--untracked"]
        for term in terms:
            arguments += ["-e", term]
        output = git(root, *arguments, "--", ".", *(f":!{prefix}" for prefix in SKIP_PREFIXES), timeout=120)
        if output is not None or git(root, "rev-parse", "--git-dir") is not None:
            sizes: dict[str, bool] = {}
            for record in (output or "").splitlines():
                parts = record.split("\0", 2)
                if len(parts) != 3 or not parts[1].isdigit():
                    continue
                path = parts[0]
                if path not in sizes:
                    try:
                        sizes[path] = (root / path).stat().st_size <= 400_000
                    except OSError:
                        sizes[path] = False
                if sizes[path]:
                    yield path, int(parts[1]), parts[2]
            return
    for relative in files:
        text = read_text_file(root, relative, limit=400_000)
        for number, line in enumerate((text or "").splitlines(), start=1):
            lowered = line.lower()
            if any(term in lowered for term in terms):
                yield relative, number, line


def where(root: Path, query: str, limit: int = 20) -> list[str]:
    """Rank paths, symbols, headings, and failure-memory lines matching the query."""
    terms = [term for term in WORD.findall(query.lower()) if len(term) > 1]
    if not terms:
        return []
    files = [path for path in repository_files(root) if not path.startswith(SKIP_PREFIXES)]
    doc_bindings = bindings(root, files)
    hits: list[tuple[int, str]] = []
    for relative in files:
        path_score = _score(terms, relative)
        if path_score:
            owned = owners(doc_bindings, relative)
            suffix = f"  (documented in {', '.join(owned)})" if owned else ""
            hits.append((path_score * 3, f"{relative}  [path]{suffix}"))
    for relative, number, line in _candidate_lines(root, files, terms):
        is_memory = relative in MEMORY_FILES or relative.startswith("docs/incidents/")
        kind = None
        match = SYMBOL.match(line)
        if match:
            kind, label = "symbol", match.group(1)
        else:
            heading = HEADING.match(line) if relative.endswith(".md") else None
            if heading:
                kind, label = "heading", heading.group(1)
            elif is_memory and line.strip():
                kind, label = "seen-before", line
        if not kind:
            continue
        score = _score(terms, label)
        if score:
            weight = {"symbol": 3, "heading": 2, "seen-before": 3}[kind]
            hits.append((score * weight, f"{relative}:{number}  [{kind}] {_short(label)}"))
    hits += _capability_hits(root, terms, query)
    hits.sort(key=lambda hit: (-hit[0], hit[1]))
    return [line for _, line in hits[:limit]]


def _capability_hits(root: Path, terms: list[str], query: str) -> list[tuple[int, str]]:
    """Capabilities of every kind and pack whose name or description matches, and rules scoped to a queried path."""
    registry = Registry(root)
    hits = []
    for item in registry.items:
        if item.kind == "doc":
            continue  # documents are found by path and heading above
        state = "" if registry.enabled(item) else (", off" if item.kind == "pack" else f", pack {item.pack} off")
        score = _score(terms, f"{item.name} {item.description}")
        if item.kind == "rule" and any(path_matches(query.strip(), pattern) for pattern in item.fields["scope"]):
            score += len(terms) + 2
        if score:
            hits.append((score * 4, f"{item.path}  [{item.kind}{state}] {item.name}: {_short(item.description, 80)}"))
    return hits


def _stem(word: str) -> str:
    for suffix in ("ing", "ers", "er", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _tokens(text: str) -> set[str]:
    stop = {"the", "and", "for", "use", "with", "that", "this", "into", "from", "when", "your", "are", "or", "a", "to", "of", "in", "an", "it", "on", "is", "be", "by"}
    return {_stem(word) for word in WORD.findall(text.lower()) if word not in stop and len(word) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


def skill_overlap(root: Path, description: str, name: str = "", limit: int = 5) -> list[tuple[float, str, str]]:
    """Similarity of a proposed capability to existing capabilities of every kind and pack (0..1).

    Description word overlap, plus half the overlap of the names when a name is
    proposed, so `handover-writer` is caught next to `agent-handover`.
    """
    proposed = _tokens(description)
    proposed_name = _tokens(name.replace("-", " "))
    if not proposed:
        return []
    candidates = [(item.kind, item.name, item.description) for item in Registry(root).items]
    scored = []
    for kind, existing_name, text in candidates:
        score = _jaccard(proposed, _tokens(text)) + 0.5 * _jaccard(proposed_name, _tokens(existing_name.replace("-", " ")))
        if score > 0:
            scored.append((min(score, 1.0), f"{kind}:{existing_name}", _short(text, 100)))
    scored.sort(key=lambda item: -item[0])
    return scored[:limit]
