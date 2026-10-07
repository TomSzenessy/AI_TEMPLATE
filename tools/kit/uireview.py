"""`make ui-review`: screenshot the real build so an agent has to look at it.

For every active product surface with a `preview` table in project.toml:

    [surfaces.preview]
    command = ["npm", "run", "dev", "--", "--port", "{port}"]
    url = "http://localhost:{port}"
    routes = ["/", "/settings"]
    states = { "with-data" = "app/review-states/with-data.json" }   # optional

it starts the preview on a free port (the `{port}` placeholder), refuses to
review a server it did not start, captures each route (and each storage state) at phone
and desktop sizes in light and dark mode with a pinned Playwright, stops the
server, and writes `.agent/reviews/<run>/REVIEW.md`. The run counts only after
its Verdict line is filled; a later change to the surface makes it stale, and
the change gate reports stale or unreviewed UI.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import setting
from .core import RepoctlError, ensure_inside_root, load_project, read_text_file, repository_files
from .product import is_product, is_ui, product_surfaces

REVIEWS = ".agent/reviews"
LATEST = f"{REVIEWS}/latest.json"
VIEWPORTS = {"phone": "390,844", "desktop": "1440,900"}
SCHEMES = ("light", "dark")
CHROME_PATHS = ("/Applications/Google Chrome.app", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable")
VERDICT_PENDING = "Verdict: pending"


def surface_digest(root: Path, path: str) -> str:
    """Content digest of a surface's tracked and untracked (non-ignored) files."""
    digest = hashlib.sha256()
    prefix = path.rstrip("/") + "/"
    for relative in repository_files(root):
        if relative.startswith(prefix):
            digest.update(relative.encode())
            try:
                digest.update((root / relative).read_bytes())
            except OSError:
                continue
    return digest.hexdigest()


def _latest(root: Path) -> dict:
    try:
        data = json.loads((root / LATEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def review_status(root: Path) -> list[str]:
    """Findings for UI surfaces without a fresh, judged review (empty when fine)."""
    project = load_project(root)
    if not (is_product(project) and is_ui(root, project)):
        return []
    latest = _latest(root)
    findings = []
    for surface in product_surfaces(project):
        identifier, path = str(surface.get("id")), str(surface.get("path", "."))
        if not isinstance(surface.get("preview"), dict):
            continue
        record = latest.get(identifier)
        if not record:
            findings.append(f"surface {identifier} has never had a UI review (make ui-review)")
            continue
        if record.get("digest") != surface_digest(root, path):
            findings.append(f"surface {identifier} changed since its last UI review (make ui-review)")
            continue
        review = read_text_file(root, f"{record.get('run')}/REVIEW.md") or ""
        if VERDICT_PENDING in review or "Verdict:" not in review:
            findings.append(f"{record.get('run')}/REVIEW.md has no verdict yet: look at every screenshot and record it")
    return findings


def _browser_arguments() -> list[str]:
    if any(Path(path).exists() for path in CHROME_PATHS) or shutil.which("google-chrome"):
        return ["--channel", "chrome"]  # the installed Chrome: nothing to download
    return ["-b", "chromium"]


def _answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except OSError:
        return False


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_for(url: str, server: subprocess.Popen, timeout: float) -> None:
    """Wait until our own preview answers; fail fast if it died instead."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RepoctlError(f"preview command exited with code {server.returncode} before answering at {url}")
        if _answers(url):
            return
        time.sleep(0.5)
    raise RepoctlError(f"preview did not answer at {url} within {timeout:.0f}s")


def run_review(root: Path) -> int:
    project = load_project(root)
    surfaces = [s for s in product_surfaces(project) if isinstance(s.get("preview"), dict)]
    if not surfaces:
        raise RepoctlError("no surface declares a [surfaces.preview] table (command, url, routes); see docs/building.md")
    if shutil.which("npx") is None:
        raise RepoctlError("npx (Node.js) is required for screenshots; install Node 18+")
    version = str(setting(root, "playwright_version"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = f"{REVIEWS}/{stamp}"
    out = ensure_inside_root(root, root / run, "review folder")
    out.mkdir(parents=True, exist_ok=True)
    latest = _latest(root)
    shots: list[str] = []
    for surface in surfaces:
        identifier, path = str(surface.get("id")), str(surface.get("path", "."))
        preview = surface["preview"]
        command, url = preview.get("command"), str(preview.get("url", ""))
        routes = preview.get("routes") or ["/"]
        states = {"default": None, **(preview.get("states") or {})}
        if not (isinstance(command, list) and command and url.startswith("http://localhost")):
            raise RepoctlError(f"surface {identifier}: preview needs command = [...] and url = \"http://localhost:{{port}}\"")
        # {port} placeholders get a free port per run, so another dev server can never be reviewed by mistake.
        port = str(_free_port())
        command = [str(part).replace("{port}", port) for part in command]
        url = url.replace("{port}", port)
        if _answers(url):
            raise RepoctlError(
                f"surface {identifier}: something already answers at {url} before the preview started; "
                "use a {port} placeholder in the preview command and url, or stop the other server"
            )
        cwd = ensure_inside_root(root, root / path, f"surface {identifier} path")
        server = subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            _wait_for(url, server, float(preview.get("timeout", 60)))
            for route in routes:
                for state, storage in states.items():
                    for size, viewport in VIEWPORTS.items():
                        for scheme in SCHEMES:
                            name = f"{identifier}{route.strip('/').replace('/', '-') or '-home'}-{state}-{size}-{scheme}.png"
                            arguments = ["npx", "-y", f"playwright@{version}", "screenshot", *_browser_arguments(),
                                         "--viewport-size", viewport, "--color-scheme", scheme,
                                         "--wait-for-timeout", "800", "--full-page"]
                            if storage:
                                arguments += ["--load-storage", str(ensure_inside_root(root, root / storage, "storage state"))]
                            result = subprocess.run([*arguments, url.rstrip("/") + route, str(out / name)],
                                                    cwd=root, capture_output=True, text=True, timeout=180, check=False)
                            if result.returncode != 0:
                                hint = "npx playwright@" + version + " install chromium"
                                raise RepoctlError(f"screenshot failed for {name}: {result.stderr.strip()[-300:]} (try: {hint})")
                            shots.append(name)
        finally:
            try:
                os.killpg(server.pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                server.terminate()
        latest[identifier] = {"digest": surface_digest(root, path), "run": run, "at": stamp}
    checklist = "\n".join(f"- [ ] {shot}" for shot in shots)
    (out / "REVIEW.md").write_text(
        f"# UI review {stamp}\n\n"
        "Open every screenshot and judge it against the ux-quality skill, docs/design.md, and the design\n"
        "references in docs/product/research.md. A reviewer that did not look at the images must not\n"
        "write a verdict.\n\n"
        "## Screenshots\n\n" + checklist + "\n\n"
        "## Findings (screenshot, region, problem, fix)\n\n- \n\n"
        "## Bar\n\n- Hierarchy, spacing rhythm, type scale, and contrast hold up next to the references\n"
        "- Every state (empty, loading, error, filled) looks designed, not default\n"
        "- Touch targets at least 44 pt; nothing clipped or overflowing at phone width\n"
        "- Light and dark both intentional\n\n"
        f"{VERDICT_PENDING}  (replace with: Verdict: pass | fix — <one line>)\n",
        encoding="utf-8",
    )
    (root / LATEST).write_text(json.dumps(latest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(shots)} screenshot(s) in {run}/. Look at each one, record findings and the verdict in {run}/REVIEW.md;")
    print("fix and re-run until the verdict is pass. Cite the run folder as evidence in docs/product/features.csv.")
    return 0
