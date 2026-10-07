"""`make help`: the command listing, rendered from the registry.

A leaf so `derive` (which fences the same text into the README) and `commands`
(which prints it) share one renderer without importing each other.
"""

from __future__ import annotations

# make help groups, in display order.
GROUPS = {
    "session": "EVERY SESSION (this is all most tasks need)",
    "extend": "EXTEND THE SYSTEM (one path for every kind of capability)",
    "when-needed": "WHEN NEEDED",
    "setup": "PROJECT SETUP AND MAINTENANCE",
}
# Targets the Makefile writes by hand because they chain other targets or run the test suites.
RECIPES = {
    "done": ("session", "make done", 'Before saying "done": heal derived files, gates, all tests'),
    "verify": ("setup", "make verify", "Tests, every surface's verification, and doctor (CI runs this)"),
    "test": ("setup", "make test", "The kit's and every skill's unit tests"),
    "test-future": ("setup", "make test-future", "The suite 800 days ahead: catches checks that rot with the calendar"),
}


def help_text(registry) -> str:
    """`make help`: every command of an enabled pack, grouped; disabled packs are named, not hidden."""
    rows: dict[str, list[tuple[str, str]]] = {group: [] for group in GROUPS}
    off: list[str] = []
    for item in registry.of("command", enabled_only=False):
        if item.fields["make"] is None or item.name == "help":
            continue
        if not registry.enabled(item):
            off.append(item.name)
            continue
        group = item.fields["group"] if item.fields["group"] in GROUPS else "when-needed"
        rows[group].append((item.fields["usage"] or f"make {item.name}", item.description))
    for group, usage, text in RECIPES.values():
        rows[group].append((usage, text))
    lines = []
    for group, title in GROUPS.items():
        lines += ([""] if lines else []) + [title]
        for usage, text in rows[group]:
            lines.append(f"  {usage:<34} {text}" if len(usage) <= 34 else f"  {usage}\n  {'':<34} {text}")
    if off:
        lines += ["", f"Packs switched off hide: {', '.join(sorted(off))} (make capabilities shows how to enable them)"]
    return "\n".join(lines)
