"""Every derived file and block, rendered from its single source.

- Host adapters (`.claude/`, `.mcp.json`) from `.agents/` (skills, roles, MCP routes).
- The documentation index block in `docs/README.md` from each document's
  `<!-- index: -->` declaration.
- The README description block from `project.toml [repository].description`.
- The role table in `docs/delegation.md` from `.agents/agents/*.md` frontmatter.
- The global rules block in `AGENTS.md` from `.agents/rules/*.md` without a scope.
- The command block in the Makefile (or `kit.mk` after `make adopt`) from the
  `@command` declarations (docs/adr/0002-one-capability-model.md).

`make sync` writes them, the after-edit hook heals them, and `make check`
fails on drift, so nobody (human or agent) maintains a derived copy by hand.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import adapters, docsync
from .core import ensure_inside_root, load_project, read_text_file, repository_files
from .registry import Registry

BLOCK = "<!-- repoctl:{name} -->\n{body}\n<!-- /repoctl:{name} -->"
MAKE_BLOCK = "# <repoctl:{name}>\n{body}\n# </repoctl:{name}>"
INDEX_DOC = "docs/README.md"
DELEGATION_DOC = "docs/delegation.md"


def render_roles(registry: Registry) -> str:
    rows = [
        f"| [`{role.name}`](../{role.path}) | {role.fields['access']}, {role.fields['tier']} | {role.description} |"
        for role in registry.of("agent", enabled_only=False)
    ]
    return "| Role | Access, tier | Use it when |\n|---|---|---|\n" + "\n".join(rows)


def render_rules(registry: Registry) -> str:
    rules = [rule for rule in registry.of("rule") if not rule.fields["scope"]]
    lines = [f"- {rule.description} ([`{rule.name}`]({rule.path}))" for rule in rules]
    return "\n".join(lines) or "- none yet (`make new KIND=rule`)"


def _make_argument(argument) -> str:
    if argument.boolean:
        return f"$(if $(filter 1 yes true,$({argument.var})),{argument.flags[0]},)"
    if argument.positional:
        return f'"$${{{argument.var}}}"'
    return f'$(if $({argument.var}),{argument.flags[0]} "$${{{argument.var}}}",)'


def render_commands(registry: Registry) -> str:
    """Make targets for every command: recipes pass make variables as data, never as shell source."""
    commands = [item for item in registry.of("command", enabled_only=False) if item.fields["make"] is not None]
    lines = [".PHONY: " + " ".join(item.fields["target"] for item in commands)]
    for item in commands:
        lines += ["", f"{item.fields['target']}: python-check"]
        if item.fields["make"]:
            lines.append("\t" + item.fields["make"])
            continue
        arguments = [argument for argument in item.fields["args"] if argument.var]
        for argument in arguments:
            if argument.hint:
                lines.append(f"\t$(if $({argument.var}),,$(error {argument.hint}))")
        parts = ["@$(REPOCTL)", item.name, *(_make_argument(argument) for argument in arguments)]
        if item.fields["make_extra"]:
            parts.append(item.fields["make_extra"])
        lines.append("\t" + " ".join(parts))
    return "\n".join(lines)


def replace_block(text: str, name: str, body: str) -> str:
    pattern = re.compile(rf"<!-- repoctl:{name} -->\n.*?<!-- /repoctl:{name} -->", re.DOTALL)
    return pattern.sub(lambda _: BLOCK.format(name=name, body=body), text, count=1)


def replace_make_block(text: str, name: str, body: str) -> str:
    pattern = re.compile(rf"(?m)^# <repoctl:{name}>\n.*?^# </repoctl:{name}>", re.DOTALL)
    return pattern.sub(lambda _: MAKE_BLOCK.format(name=name, body=body), text, count=1)


def description(project: dict[str, object]) -> str:
    repository = project.get("repository", {})
    value = repository.get("description", "") if isinstance(repository, dict) else ""
    return str(value).strip()


def render_blocks(root: Path) -> dict[str, str]:
    """Hand-written files whose marked blocks are generated."""
    files: dict[str, str] = {}
    registry = Registry(root)
    index = read_text_file(root, INDEX_DOC)
    if index is not None and "<!-- repoctl:index -->" in index:
        files[INDEX_DOC] = replace_block(index, "index", docsync.render_index(root, repository_files(root), INDEX_DOC))
    delegation = read_text_file(root, DELEGATION_DOC)
    if delegation is not None and "<!-- repoctl:roles -->" in delegation:
        files[DELEGATION_DOC] = replace_block(delegation, "roles", render_roles(registry))
    agents = read_text_file(root, "AGENTS.md")
    if agents is not None and "<!-- repoctl:rules -->" in agents:
        files["AGENTS.md"] = replace_block(agents, "rules", render_rules(registry))
    for makefile in ("kit.mk", "Makefile"):  # after make adopt, the kit's targets live in kit.mk
        text = read_text_file(root, makefile)
        if text is not None and "# <repoctl:commands>" in text:
            block = render_commands(registry)
            if makefile == "kit.mk":
                from .adopt import rename_kit_targets
                block = rename_kit_targets(read_text_file(root, "Makefile") or "", block)
            files[makefile] = replace_make_block(text, "commands", block)
            break
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
    kit_makefiles = [name for name in ("kit.mk", "Makefile") if "$(REPOCTL)" in (read_text_file(root, name) or "")]
    if kit_makefiles and not any("# <repoctl:commands>" in (read_text_file(root, name) or "") for name in kit_makefiles):
        errors.append(f"{kit_makefiles[0]} lost its generated command block: restore the `# <repoctl:commands>` and "
                      "`# </repoctl:commands>` marker lines from the template, then run `make sync`")
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
