"""Drive a product to a verifiable bar: feature list, research record, and `make next`.

Hygiene checks prove the repository is tidy; they cannot prove the product is
complete or good. This module makes the product bar explicit and checkable:

- `docs/product/features.csv` lists every feature with priority, status,
  evidence, and acceptance. A `yes` or `partial` row must cite evidence that
  exists (a test file, a review folder, a doc). Weights match parity-check:
  must 3, should 2, could 1; yes 1, partial 0.5.
- `docs/product/research.md` records the comparable products, user complaints,
  and design references the feature list and design were derived from.
- `next_step` reads repository state and returns the single next step, so any
  model follows the same path from intake to launch.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .config import setting
from .core import RepoctlError, declared_surfaces, load_project, read_text_file

FEATURES = "docs/product/features.csv"
RESEARCH = "docs/product/research.md"
WEIGHT = {"must": 3, "should": 2, "could": 1}
CREDIT = {"yes": 1.0, "partial": 0.5, "no": 0.0}
STATUSES = {"yes", "partial", "no", "skip"}
URL = re.compile(r"https?://[^\s)>\]]+")


def is_product(project: dict[str, object]) -> bool:
    return project.get("kind") != "template"


def is_ui(root: Path, project: dict[str, object]) -> bool:
    return project.get("kind") in setting(root, "ui_kinds")


def product_surfaces(project: dict[str, object]) -> list[dict[str, object]]:
    return [
        surface for surface in declared_surfaces(project)
        if surface.get("status", "active") == "active" and surface.get("kind") != "template"
    ]


def load_features(root: Path) -> list[dict[str, str]]:
    text = read_text_file(root, FEATURES)
    if text is None:
        return []
    rows = []
    for number, row in enumerate(csv.DictReader(text.splitlines()), start=2):
        feature = (row.get("feature") or "").strip()
        if not feature:
            continue
        priority = (row.get("priority") or "").strip().lower()
        status = (row.get("status") or "no").strip().lower()
        if priority not in WEIGHT:
            raise RepoctlError(f"{FEATURES}:{number}: priority must be must, should, or could")
        if status not in STATUSES:
            raise RepoctlError(f"{FEATURES}:{number}: status must be yes, partial, no, or skip")
        rows.append({
            "line": str(number), "feature": feature, "priority": priority, "status": status,
            "area": (row.get("area") or "").strip(), "evidence": (row.get("evidence") or "").strip(),
            "acceptance": (row.get("acceptance") or "").strip(),
        })
    return rows


def score(rows: list[dict[str, str]]) -> tuple[float, list[dict[str, str]]]:
    """Weighted completeness (0-100) and the open must rows, in file order."""
    counted = [row for row in rows if row["status"] != "skip"]
    total = sum(WEIGHT[row["priority"]] for row in counted)
    earned = sum(WEIGHT[row["priority"]] * CREDIT[row["status"]] for row in counted)
    open_must = [row for row in counted if row["priority"] == "must" and row["status"] != "yes"]
    return (100.0 * earned / total if total else 0.0), open_must


REVIEW_LOG = "docs/product/ui-reviews.md"
TEST_NAME = re.compile(r"(?i)(^|/)(tests?|__tests__|e2e|spec)/|[._-](test|spec)\.")


def _evidence_paths(evidence: str) -> list[str]:
    paths = []
    for token in re.split(r"[;\s,]+", evidence):
        path = token.strip("`").split("::", 1)[0].split("#", 1)[0]
        path = re.sub(r":\d+$", "", path)
        if path:
            paths.append(path)
    return paths


def _evidence_problem(root: Path, row: dict[str, str]) -> str | None:
    """None when the evidence is acceptable for this row."""
    paths = _evidence_paths(row["evidence"])
    if not paths:
        return "cites no evidence"
    missing = [path for path in paths if not (root / path).is_file()]
    if missing:
        return f"cites evidence that is not an existing file: {', '.join(missing)}"
    if row["priority"] == "must" and row["status"] == "yes" and not any(
        TEST_NAME.search(path) or path == REVIEW_LOG for path in paths
    ):
        return f"is a must feature marked yes without a test file or {REVIEW_LOG} among its evidence"
    return None


def feature_errors(root: Path) -> list[str]:
    if read_text_file(root, FEATURES) is None:
        return []
    errors = []
    try:
        rows = load_features(root)
    except RepoctlError as error:
        return [str(error)]
    if rows and not any(row["priority"] == "must" for row in rows):
        errors.append(f"{FEATURES}: needs at least one must row; a product without must features has no definition of done")
    for row in rows:
        problem = _evidence_problem(root, row) if row["status"] in {"yes", "partial"} else None
        if problem:
            errors.append(
                f"{FEATURES}:{row['line']}: '{row['feature']}' ({row['status']}) {problem} "
                f"(cite test files and, for UI, {REVIEW_LOG})"
            )
        if row["priority"] == "must" and not row["acceptance"]:
            errors.append(f"{FEATURES}:{row['line']}: must feature '{row['feature']}' needs an acceptance criterion")
    return errors


def research_errors(root: Path, project: dict[str, object]) -> list[str]:
    vision = project.get("vision", {})
    accepted = isinstance(vision, dict) and vision.get("status") == "accepted"
    # Enforced for UI products (references matter most there); make next recommends it for all.
    if not (accepted and is_product(project) and is_ui(root, project) and product_surfaces(project)):
        return []
    text = read_text_file(root, RESEARCH) or ""
    sources = set(URL.findall(text))
    if len(sources) < 3:
        return [
            f"{RESEARCH} needs at least three cited sources (comparable products, user reviews, design "
            f"references) before building; found {len(sources)}. Run the research step of product-kickoff."
        ]
    return []


def _stack_accepted(root: Path) -> bool:
    text = read_text_file(root, "docs/STACK-DECISION.md") or ""
    return bool(re.search(r"(?im)^\W*status\W*:?\W*accepted\b", text))


def next_step(root: Path) -> dict[str, str]:
    """The single next step from repository state: phase, action, guide, verify."""
    from .uireview import review_status  # local import: uireview depends on this module

    project = load_project(root)
    if not is_product(project):
        return {"phase": "template", "action": "Maintain the template: fix `make garden` findings, keep evals green.",
                "guide": "docs/self-healing.md", "verify": "make done"}
    vision = project.get("vision", {})
    ui = is_ui(root, project)
    steps = [
        (not (isinstance(vision, dict) and vision.get("status") == "accepted"), "intake",
         "Ask the owner the kickoff questions (one round, with recommendations) and record VISION.md as accepted.",
         "product-kickoff skill, steps 1-2", "VISION.md Status: accepted"),
        (len(set(URL.findall(read_text_file(root, RESEARCH) or ""))) < 3, "research",
         f"Research comparable products, real user complaints, and design references; write {RESEARCH} with cited URLs "
         "(first line under the title: <!-- index: extend | Comparable products and our angle | Scoping features -->).",
         "researcher role; product-recon and review-mining skills; browse the web",
         f"{RESEARCH} cites at least three sources"),
        (not any(row["priority"] == "must" for row in load_features(root)), "features",
         f"Write {FEATURES} from the research and owner answers, then append the relevant production rows "
         "(.agents/skills/product-kickoff/production-features.csv). Every must row gets an acceptance criterion.",
         "product-kickoff skill, step 4", "make next shows the build phase"),
        (ui and len(read_text_file(root, "docs/design.md") or "") < 300, "design",
         "Render two or three mockup directions, choose with the owner, and record docs/design.md (direction, tokens, references).",
         "product-kickoff step 3; ux-quality skill", "docs/design.md exists"),
        (not _stack_accepted(root), "stack",
         "Record the stack decision (verified current versions) in docs/STACK-DECISION.md with Status: accepted.",
         "product-kickoff step 2; researcher role for versions", "docs/STACK-DECISION.md Status: accepted"),
        (not product_surfaces(project), "skeleton",
         "Scaffold the walking skeleton and declare its surface in project.toml with verification and garden commands.",
         "stack-foundation skill", "make done"),
    ]
    for pending, phase, action, guide, verify in steps:
        if pending:
            return {"phase": phase, "action": action, "guide": guide, "verify": verify}
    if project.get("kind") in setting(root, "preview_kinds"):
        missing = [str(s.get("id")) for s in product_surfaces(project) if not isinstance(s.get("preview"), dict)]
        if missing:
            return {"phase": "preview", "action": f"Declare a [surfaces.preview] table (command, url, routes) for: {', '.join(missing)}.",
                    "guide": "docs/building.md#ui-review", "verify": "make ui-review"}
    rows = load_features(root)
    percent, open_must = score(rows)
    if open_must:
        row = open_must[0]
        return {"phase": "build",
                "action": f"Build '{row['feature']}' ({row['area'] or 'core'}): {row['acceptance'] or 'see features.csv'}. "
                          f"{len(open_must)} must feature(s) open; product {percent:.0f}% complete.",
                "guide": "implementer role per slice; ux-quality for UI; mark status=yes with evidence when it passes",
                "verify": "make done, then make ui-review for UI changes"}
    if ui:
        stale = review_status(root)
        if stale:
            return {"phase": "review", "action": "Run the UI review and fix what it shows: " + "; ".join(stale),
                    "guide": "make ui-review, then the critic role on the screenshots (ux-quality skill)",
                    "verify": f"latest entry in {REVIEW_LOG} matches the code, every screenshot ticked, Verdict: pass"}
    open_should = [row for row in rows if row["priority"] == "should" and row["status"] not in {"yes", "skip"}]
    if open_should:
        row = open_should[0]
        return {"phase": "polish", "action": f"Build should-feature '{row['feature']}': {row['acceptance'] or 'see features.csv'}.",
                "guide": "implementer role; ux-quality", "verify": "make done, make ui-review"}
    return {"phase": "launch",
            "action": f"Product {percent:.0f}% complete with every must and should feature evidenced. Run the release "
                      "sequence in docs/production.md and an independent critic pass on the whole product.",
            "guide": "docs/production.md; critic role", "verify": "make readiness"}


def print_next(root: Path) -> None:
    step = next_step(root)
    print(f"Next ({step['phase']}): {step['action']}")
    print(f"How: {step['guide']}")
    print(f"Done when: {step['verify']}")


def product_summary(root: Path) -> str | None:
    """One line for `make done`: completeness and what still blocks 'product complete'."""
    project = load_project(root)
    if not is_product(project) or read_text_file(root, FEATURES) is None:
        return None
    try:
        percent, open_must = score(load_features(root))
    except RepoctlError as error:
        return f"Product: {error}"
    if open_must:
        names = ", ".join(row["feature"] for row in open_must[:3]) + (" …" if len(open_must) > 3 else "")
        return f"Product {percent:.0f}% complete; NOT done: {len(open_must)} must feature(s) open ({names}). Run make next."
    return f"Product {percent:.0f}% complete; all must features evidenced. Run make next for the remaining steps."
