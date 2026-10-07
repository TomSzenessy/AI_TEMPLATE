"""Which declared surfaces make a product, and which of them have a user interface.

A leaf shared by `product` (the next step) and `uireview` (the review gate),
so neither imports the other.
"""

from __future__ import annotations

from pathlib import Path

from .config import setting
from .core import declared_surfaces


def is_product(project: dict[str, object]) -> bool:
    return project.get("kind") != "template"


def is_ui(root: Path, project: dict[str, object]) -> bool:
    return project.get("kind") in setting(root, "ui_kinds")


def product_surfaces(project: dict[str, object]) -> list[dict[str, object]]:
    return [
        surface for surface in declared_surfaces(project)
        if surface.get("status", "active") == "active" and surface.get("kind") != "template"
    ]
