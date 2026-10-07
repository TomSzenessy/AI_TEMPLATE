# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Jake Schincariol. Adapted from https://github.com/Jakeschincariol/replica-skill (revision: see project.toml [[skills]]).
"""Load a tool script from this skill's folder (the folder names have hyphens)."""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = os.path.basename(ROOT).replace("-", "_") + "_"  # derived from the folder, so every copy is byte-identical


def load(name):
    path = os.path.join(ROOT, name + ".py")
    spec = importlib.util.spec_from_file_location(PREFIX + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
