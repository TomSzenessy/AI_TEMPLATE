"""`make ui-review`: screenshot the real build so an agent has to look at it.

For every active product surface with a `preview` table in project.toml:

    [surfaces.preview]
    command = ["npm", "run", "dev", "--", "--port", "{port}", "--strictPort"]
    url = "http://localhost:{port}"
    routes = ["/", "/settings"]
    states = { "with-data" = "app/review-states/with-data.json" }   # optional

it starts the preview on a free port (the `{port}` placeholder), refuses to
review a server it did not start, captures each route and storage state at
phone and desktop sizes in light and dark mode with a pinned Playwright, and
stops the server. Screenshots stay local in `.agent/reviews/<run>/`; the review
record is appended to the tracked `docs/product/ui-reviews.md` (surface
digests, the screenshot list, findings, verdict), so every clone sees the same
review history. A surface counts as reviewed when its latest record matches
the current code and the verdict is `pass`. That is a feature and launch gate
(`make next`, `make readiness` from private-preview on), not a per-commit one.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import derive
from .config import setting
from .core import (
    RepoctlError, ensure_inside_root, load_project, normalized_relative_path, read_text_file, repository_files,
)
from .product import is_product, is_ui, product_surfaces

SHOTS = ".agent/reviews"
LOG = "docs/product/ui-reviews.md"
LOG_HEADER = (
    "# UI reviews\n\n"
    "<!-- index: launch | Screenshot review history: verdicts, findings, reviewed code digests | "
    "judging UI quality or citing review evidence -->\n\n"
    "Appended by `make ui-review` (docs/building.md). Screenshots are local in `.agent/reviews/<run>/`; "
    "look at each one, record findings, then set the verdict to pass or fix.\n"
)
VIEWPORTS = {"phone": "390,844", "desktop": "1440,900"}
SCHEMES = ("light", "dark")
CHROME_PATHS = (
    "/Applications/Google Chrome.app", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
    "/opt/google/chrome/chrome", "C:/Program Files/Google/Chrome/Application/chrome.exe",
)
ENTRY = re.compile(r"(?ms)^## Review (?P<run>\S+)\n(?P<body>.*?)(?=^## Review |\Z)")
MARKER = re.compile(r"<!-- review: (?P<surfaces>[^>]*?) -->")
SAFE = re.compile(r"[^A-Za-z0-9-]+")


def surface_digest(root: Path, path: str) -> str:
    """Content digest of a surface's tracked and untracked (non-ignored) files."""
    digest = hashlib.sha256()
    surface = normalized_relative_path(path, "path") if path.strip() else "."
    prefix = "" if surface == "." else surface + "/"  # the root surface covers every file
    for relative in repository_files(root):
        if relative == LOG or relative.startswith(SHOTS + "/"):
            continue  # the review record and its screenshots must not stale the review they describe
        if relative.startswith(prefix):
            digest.update(relative.encode())
            try:
                digest.update((root / relative).read_bytes())
            except OSError:
                continue
    return digest.hexdigest()[:16]


def preview_surfaces(project: dict[str, object]) -> list[dict[str, object]]:
    return [surface for surface in product_surfaces(project) if isinstance(surface.get("preview"), dict)]


def latest_records(root: Path) -> dict[str, tuple[str, str, str]]:
    """surface id -> (run, digest, entry body) for the newest review of each surface."""
    records: dict[str, tuple[str, str, str]] = {}
    for match in ENTRY.finditer(read_text_file(root, LOG) or ""):
        marker = MARKER.search(match.group("body"))
        if not marker:
            continue
        for pair in marker.group("surfaces").split():
            identifier, _, digest = pair.partition("=")
            records[identifier] = (match.group("run"), digest, match.group("body"))
    return records


def review_status(root: Path) -> list[str]:
    """Findings for previewable UI surfaces without a fresh, passing review."""
    project = load_project(root)
    if not (is_product(project) and is_ui(root, project)):
        return []
    records = latest_records(root)
    findings = []
    for surface in preview_surfaces(project):
        identifier = str(surface.get("id"))
        if identifier not in records:
            findings.append(f"surface {identifier} has never had a UI review (make ui-review)")
            continue
        run, digest, body = records[identifier]
        if digest != surface_digest(root, str(surface.get("path", "."))):
            findings.append(f"surface {identifier} changed since UI review {run} (make ui-review)")
        elif not re.search(r"(?m)^Verdict:\s*pass\b", body):
            findings.append(f"UI review {run} in {LOG} is not `Verdict: pass`: fix the findings and run make ui-review again")
    return findings


def _browser_arguments() -> list[str]:
    if any(Path(path).exists() for path in CHROME_PATHS) or shutil.which("google-chrome") or shutil.which("google-chrome-stable"):
        return ["--channel", "chrome"]  # the installed Chrome: nothing to download
    return ["-b", "chromium"]


def _playwright(root: Path) -> list[str]:
    """The Playwright command: an explicit [kit] pin, else an installed Playwright, else the default pin.

    An installed Playwright already has browsers that match its version (CI images and cloud
    containers ship one); forcing a different pinned version there fails on a missing browser build.
    """
    kit = load_project(root).get("kit", {})
    pinned = isinstance(kit, dict) and "playwright_version" in kit
    installed = shutil.which("playwright")
    if installed and not pinned:
        return [installed]
    return ["npx", "-y", f"playwright@{setting(root, 'playwright_version')}"]


def _answers(url: str) -> bool:
    """True when anything HTTP answers, including error statuses."""
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _stop(server: subprocess.Popen) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(server.pid, signal.SIGTERM)
        else:  # Windows: no process groups
            server.terminate()
        server.wait(timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(server.pid, signal.SIGKILL) if hasattr(os, "killpg") else server.kill()
        except OSError:
            pass


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


def _capture(root: Path, surface: dict[str, object], out: Path, playwright: list[str]) -> list[str]:
    identifier = str(surface.get("id"))
    preview = surface["preview"]
    command, url = preview.get("command"), str(preview.get("url", ""))
    if not (isinstance(command, list) and command and urlsplit(url.replace("{port}", "1")).hostname in {"localhost", "127.0.0.1"}):
        raise RepoctlError(f"surface {identifier}: preview needs command = [...] and url = \"http://localhost:{{port}}\"")
    routes = [str(route) for route in (preview.get("routes") or ["/"])]
    bad = [route for route in routes if not route.startswith("/")]
    if bad:
        raise RepoctlError(f"surface {identifier}: routes must start with '/': {', '.join(bad)}")
    states: dict[str, str | None] = {"default": None, **(preview.get("states") or {})}
    port = str(_free_port())  # {port}: a fresh free port, so another dev server is never reviewed by mistake
    command = [str(part).replace("{port}", port) for part in command]
    url = url.replace("{port}", port).rstrip("/")
    if _answers(url):
        raise RepoctlError(
            f"surface {identifier}: something already answers at {url} before the preview started; "
            "use a {port} placeholder in the preview command and url, or stop the other server"
        )
    cwd = ensure_inside_root(root, root / str(surface.get("path", ".")), f"surface {identifier} path")
    server = subprocess.Popen(command, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=hasattr(os, "killpg"))
    shots = []
    try:
        _wait_for(url, server, float(preview.get("timeout", 60)))
        for route in routes:
            for state, storage in states.items():
                for size, viewport in VIEWPORTS.items():
                    for scheme in SCHEMES:
                        name = "-".join(SAFE.sub("-", part).strip("-") or "home" for part in (identifier, route, state, size, scheme)) + ".png"
                        arguments = [*playwright, "screenshot", *_browser_arguments(),
                                     "--viewport-size", viewport, "--color-scheme", scheme,
                                     "--wait-for-timeout", "800", "--full-page"]
                        if storage:
                            arguments += ["--load-storage", str(ensure_inside_root(root, root / storage, "storage state"))]
                        result = subprocess.run([*arguments, url + route, str(out / name)],
                                                cwd=root, capture_output=True, text=True, timeout=180, check=False)
                        if result.returncode != 0:
                            raise RepoctlError(
                                f"screenshot failed for {name}: {result.stderr.strip()[-300:]} "
                                f"(try: {' '.join(playwright)} install chromium)"
                            )
                        shots.append(name)
    finally:
        _stop(server)
    return shots


def run_review(root: Path) -> int:
    project = load_project(root)
    surfaces = preview_surfaces(project)
    if not surfaces:
        raise RepoctlError("no surface declares a [surfaces.preview] table (command, url, routes); see docs/building.md")
    playwright = _playwright(root)
    if shutil.which(playwright[0]) is None:
        raise RepoctlError("npx (Node.js) is required for screenshots; install Node 18+")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ensure_inside_root(root, root / SHOTS / stamp, "review folder")
    out.mkdir(parents=True, exist_ok=True)
    shots: list[str] = []
    for surface in surfaces:
        shots += _capture(root, surface, out, playwright)
    digests = " ".join(f"{s.get('id')}={surface_digest(root, str(s.get('path', '.')))}" for s in surfaces)
    entry = (
        f"\n## Review {stamp}\n\n<!-- review: {digests} -->\n\n"
        f"Screenshots in `{SHOTS}/{stamp}/` (local); look at every one:\n\n"
        + "".join(f"- {shot}\n" for shot in shots)
        + "\nFindings (screenshot, region, problem, fix):\n\n- none yet\n\n"
        "Bar: hierarchy, spacing rhythm, type scale, and contrast hold up next to the references; every\n"
        "state looks designed; touch targets at least 44 pt; nothing clipped at phone width; light and dark\n"
        "both intentional.\n\nVerdict: pending\n"
    )
    log = ensure_inside_root(root, root / LOG, "review log")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text((read_text_file(root, LOG) or LOG_HEADER) + entry, encoding="utf-8")
    derive.sync(root)  # a new log must appear in the docs index, or make check fails on the review itself
    print(f"{len(shots)} screenshot(s) in {SHOTS}/{stamp}/; review entry appended to {LOG}.")
    print("Open each image, record findings, and set `Verdict: pass` or `Verdict: fix`; fix and re-run until pass.")
    print(f"Cite `{LOG}` as evidence in docs/product/features.csv once the verdict is pass.")
    return 0
