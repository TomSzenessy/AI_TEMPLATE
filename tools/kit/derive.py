"""Every derived file and block, rendered from its single source.

- Host adapters (`.claude/`, `.mcp.json`) from `.agents/` and `resources.toml`.
- The documentation index block in `docs/README.md` from each document's
  `<!-- index: -->` declaration.
- The README description block from `project.toml [repository].description`.
- The role table in `docs/delegation.md` from `.agents/agents/*.md` frontmatter.

`make sync` writes them, the after-edit hook heals them, and `make check`
fails on drift, so nobody (human or agent) maintains a derived copy by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import adapters, docsync
from .core import ensure_inside_root, load_project, read_text_file, repository_files

BLOCK = "<!-- repoctl:{name} -->\n{body}\n<!-- /repoctl:{name} -->"
INDEX_DOC = "docs/README.md"
DELEGATION_DOC = "docs/delegation.md"


def render_roles(root: Path) -> str:
    rows = [
        f"| [`{role['name']}`](../.agents/agents/{role['name']}.md) | {role['access']}, {role['tier']} | {role['description']} |"
        for role in adapters.canonical_roles(root)
    ]
    return "| Role | Access, tier | Use it when |\n|---|---|---|\n" + "\n".join(rows)


def replace_block(text: str, name: str, body: str) -> str:
    pattern = re.compile(rf"<!-- repoctl:{name} -->\n.*?<!-- /repoctl:{name} -->", re.DOTALL)
    return pattern.sub(lambda _: BLOCK.format(name=name, body=body), text, count=1)


def description(project: dict[str, object]) -> str:
    repository = project.get("repository", {})
    value = repository.get("description", "") if isinstance(repository, dict) else ""
    return str(value).strip()


def render_blocks(root: Path) -> dict[str, str]:
    """Hand-written files whose marked blocks are generated."""
    files: dict[str, str] = {}
    index = read_text_file(root, INDEX_DOC)
    if index is not None and "<!-- repoctl:index -->" in index:
        files[INDEX_DOC] = replace_block(index, "index", docsync.render_index(root, repository_files(root), INDEX_DOC))
    delegation = read_text_file(root, DELEGATION_DOC)
    if delegation is not None and "<!-- repoctl:roles -->" in delegation:
        files[DELEGATION_DOC] = replace_block(delegation, "roles", render_roles(root))
    readme = read_text_file(root, "README.md")
    if readme is not None and "<!-- repoctl:description -->" in readme:
        text = description(load_project(root)) or "Describe this project in `project.toml` `[repository].description`, then run `make sync`."
        files["README.md"] = replace_block(readme, "description", text)
    return files


def render_all(root: Path) -> dict[str, str]:
    return {**adapters.render(root), **render_blocks(root)}


def drift(root: Path) -> list[str]:
    """Derived content that differs from its source, plus stray host files."""
    expected = render_all(root)
    hosts = adapters.configured_hosts(root)
    errors = [
        f"derived file out of date: {relative} (run `make sync`)"
        for relative, content in sorted(expected.items())
        if read_text_file(root, relative) != content
    ]
    errors += [
        f"hand-authored file in a generated host directory: {relative} (move its content to .agents/ and run `make sync`)"
        for relative in adapters.host_files(root, hosts)
        if relative not in expected
    ]
    return errors


def sync(root: Path) -> list[str]:
    """Write derived content and remove generated orphans; return what changed."""
    expected = render_all(root)
    changed = []
    for relative, content in sorted(expected.items()):
        if read_text_file(root, relative) != content:
            target = ensure_inside_root(root, root / relative, "derived path")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            changed.append(relative)
    for relative in adapters.host_files(root, adapters.configured_hosts(root)):
        # Only files this generator wrote are removed; hand-authored ones stay for drift().
        if relative not in expected and adapters.GENERATED_MARK in (read_text_file(root, relative) or ""):
            stale = root / relative
            stale.unlink()
            if stale.parent != root and not any(stale.parent.iterdir()):
                stale.parent.rmdir()
            changed.append(f"removed {relative}")
    return changed
