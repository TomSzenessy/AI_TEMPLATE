"""The kit's import graph is acyclic, and its module map names every module (#48).

A cycle hidden behind a function-local import still couples two modules and
invites import-order bugs. This reads every `from .x import y` in
`tools/kit/*.py` (module level and function level) and fails on any cycle.
The one exemption is `commands.py`: its function-local imports are lazy
dispatch, kept so `repoctl help` does not load every module (startup time);
nothing imports `commands`, so they cannot close a cycle anyway.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "tools" / "kit"
DISPATCH_MODULE = "commands"


def kit_modules(kit: Path = KIT) -> set[str]:
    return {path.stem for path in kit.glob("*.py")} - {"__init__"}


def import_graph(kit: Path = KIT) -> dict[str, set[str]]:
    """module -> kit modules it imports. In the dispatch module only module-level imports count."""
    modules = kit_modules(kit)
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for name in modules:
        tree = ast.parse((kit / f"{name}.py").read_text(encoding="utf-8"))
        nodes = tree.body if name == DISPATCH_MODULE else list(ast.walk(tree))
        for node in nodes:
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                targets = [node.module.split(".")[0]] if node.module else [alias.name for alias in node.names]
                graph[name] |= {target for target in targets if target in modules and target != name}
    return graph


def find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    """One cycle as [a, b, ..., a], or None when the graph is acyclic."""
    state: dict[str, int] = {}  # 1 on the current path, 2 finished
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        path.append(node)
        for target in sorted(graph.get(node, ())):
            if state.get(target) == 1:
                return path[path.index(target):] + [target]
            if target not in state and (cycle := visit(target)):
                return cycle
        path.pop()
        state[node] = 2
        return None

    for node in sorted(graph):
        if node not in state and (cycle := visit(node)):
            return cycle
    return None


class ImportGraphTests(unittest.TestCase):
    def test_detector_finds_a_cycle(self) -> None:
        self.assertEqual(find_cycle({"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": set()}), ["a", "b", "c", "a"])
        self.assertIsNone(find_cycle({"a": {"b"}, "b": {"c"}, "c": set()}))

    def test_kit_import_graph_is_acyclic(self) -> None:
        cycle = find_cycle(import_graph())
        self.assertIsNone(cycle, "import cycle in tools/kit: " + " -> ".join(cycle or []))

    def test_nothing_imports_the_dispatch_module(self) -> None:
        importers = sorted(name for name, targets in import_graph().items() if DISPATCH_MODULE in targets)
        self.assertEqual(importers, [], "its lazy imports are exempt only because nothing imports it back")

    def test_module_map_names_every_module(self) -> None:
        modules = kit_modules()
        docstring = ast.get_docstring(ast.parse((KIT / "__init__.py").read_text(encoding="utf-8"))) or ""
        architecture = (ROOT / "docs" / "architecture" / "README.md").read_text(encoding="utf-8")
        listed = {
            "tools/kit/__init__.py": {name for name in modules if re.search(rf"\b{name}\b", docstring)},
            "docs/architecture/README.md": {name for name in modules if f"`{name}`" in architecture},
        }
        for relative, found in listed.items():
            self.assertEqual(sorted(modules - found), [], f"{relative} does not list these tools/kit modules")


if __name__ == "__main__":
    unittest.main()
