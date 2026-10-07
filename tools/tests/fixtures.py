"""Shared fixtures for the kit's test suite (#43): one builder, one CLI, isolated git.

- `run_cli` invokes `repoctl.main` in this process; the interpreter start per
  command was most of the suite's wall time.
- `build_demo`/`KitRepository` build the throwaway repository once per test
  class and copy it per test, instead of git init + derive.sync + commit per test.
- Every git command runs with the developer's global and system config switched
  off and identity from the environment: `commit.gpgsign`, `core.hooksPath` or
  `fsmonitor` in ~/.gitconfig must neither break nor change a fixture commit,
  and the suite must pass under any of them.

Nothing here depends on wall-clock, network, ambient environment, or ordering.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import unittest
from datetime import date, timedelta
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPOCTL = TOOLS / "repoctl.py"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import repoctl  # noqa: E402  the CLI entry point, called in-process
from kit import derive, docsync, registry  # noqa: E402

# Template maintenance tests (they read the template's own history, Makefile wiring or
# release material) run in the template checkout only, never in a project's copy of the suite.
IN_TEMPLATE = tomllib.loads((TOOLS.parent / "project.toml").read_text(encoding="utf-8")).get("kind") == "template"
template_only = unittest.skipUnless(IN_TEMPLATE, "template maintenance: runs in the template checkout only")


def kit_makefile(root: Path) -> str:
    """The kit's make targets: `kit.mk` in an adopted project (targets it collides on become
    `kit-<name>`), else the Makefile."""
    included = root / "kit.mk"
    return (included if included.is_file() else root / "Makefile").read_text(encoding="utf-8")


# Fixture dates follow the calendar so the suite never expires (#10).
RECENT = (date.today() - timedelta(days=30)).isoformat()

# What the developer's git config must never decide for a fixture (#43, T-09):
# no global/system config at all, and identity from the environment rather than
# from `git config user.*` argv repeated in every test.
GIT_ISOLATION = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    # No detached `gc --auto` / `maintenance`: a background git still writing into a
    # fixture's .git after the command returns makes the temp-dir cleanup fail
    # ("Directory not empty: '.git'", seen in CI on test_kit_update_ref).
    "GIT_CONFIG_COUNT": "2",
    "GIT_CONFIG_KEY_0": "gc.auto",
    "GIT_CONFIG_VALUE_0": "0",
    "GIT_CONFIG_KEY_1": "maintenance.auto",
    "GIT_CONFIG_VALUE_1": "false",
}


def clean_env(**updates: str) -> dict[str, str]:
    """The ambient environment plus git isolation plus updates, for a subprocess."""
    return {**os.environ, **GIT_ISOLATION, **updates}


@contextlib.contextmanager
def environment(updates: dict[str, str] | None = None):
    """os.environ plus git isolation plus updates for the duration, then restored."""
    saved = dict(os.environ)
    os.environ.update(GIT_ISOLATION)
    os.environ.update(updates or {})
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


@contextlib.contextmanager
def _standard_input(text: str | None):
    """Give the CLI this stdin (empty when none): never the test runner's terminal."""
    saved = sys.stdin
    sys.stdin = io.StringIO(text if text is not None else "")
    try:
        yield
    finally:
        sys.stdin = saved


def run_cli(root: Path, *arguments: str, stdin: str | None = None,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the repoctl CLI in this process; result shape matches subprocess.run."""
    out, err = io.StringIO(), io.StringIO()
    argv = ["--root", str(root), *arguments]
    with environment(env), _standard_input(stdin), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = repoctl.main(argv)
        except SystemExit as exit_:  # argparse's usage errors exit; a shell would return the code
            code = exit_.code if isinstance(exit_.code, int) else 1
    return subprocess.CompletedProcess([str(REPOCTL), *arguments], code or 0, out.getvalue(), err.getvalue())


def git_in(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """One git command in `root` under the isolated git environment."""
    return subprocess.run(["git", "-C", str(root), *arguments], check=check,
                          capture_output=True, text=True, env=clean_env())


class Scratch(unittest.TestCase):
    """A throwaway directory with write()/git()/cli() and no ambient git config."""

    def setUp(self) -> None:
        self.enterContext(environment())
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()

    def write(self, name: str, content: str | bytes) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(textwrap.dedent(content), encoding="utf-8")
        return path

    def git(self, *arguments: str) -> str:
        return git_in(self.root, *arguments).stdout

    def git_result(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return git_in(self.root, *arguments, check=False)

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def cli(self, *arguments: str, stdin: str | None = None,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return run_cli(self.root, *arguments, stdin=stdin, env=env)


DEMO_MANIFEST = """\
    schema = 1
    name = "Demo"
    kind = "web"
    phase = "development"
    [adapters]
    hosts = ["claude"]
    [budgets]
    "AGENTS.md" = 200
    [risk]
    high = ["src/auth/**"]
    low = ["docs/**"]
    """

DEMO_RESOURCES = """\
    schema = 1
    [[resources]]
    id = "docs"
    kind = "library-docs"
    source = "https://example.com/"
    trust = "official"
    access = "read-only"
    scope = "web"
    summary = "Example docs."
    """


def build_demo(root: Path) -> None:
    """The throwaway project: one bound doc, one skill, one role — built and committed once."""
    root.mkdir(parents=True, exist_ok=True)

    def write(name: str, content: str) -> None:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")

    write("project.toml", DEMO_MANIFEST)
    write("resources.toml", DEMO_RESOURCES)
    write(".agents/mcp/browser.toml", """\
        name = "browser"
        description = "Drive a browser for UI checks."
        transport = "stdio"
        command = ["npx", "-y", "@example/mcp@1.2.3"]
        enabled = true
        """)
    write("Makefile", "check:\n\t@true\nverify:\n\t@true\n")
    write("AGENTS.md", "# Agents\n")
    write("src/billing/invoice.py", "def render_invoice():\n    return 1\n")
    write("src/auth/login.py", "def login():\n    return True\n")
    write("docs/billing.md", "# Billing\n\n<!-- covers: src/billing/** -->\n\nRun `make check`.\n")
    write(".agents/skills/demo-skill/SKILL.md",
          "---\nname: demo-skill\ndescription: Render invoices for billing customers.\n---\n\n# Demo\n")
    write(".agents/agents/scout.md",
          "---\nname: scout\ndescription: Read-only locator for files.\naccess: read-only\ntier: fast\n---\n\n# Scout\n")
    git_in(root, "init", "-q", "-b", "main")
    git_in(root, "config", "user.email", "test@example.com")
    git_in(root, "config", "user.name", "Test")
    derive.sync(root)
    git_in(root, "add", "-A")
    git_in(root, "commit", "-q", "-m", "initial")


_DEMO: Path | None = None
_DEMO_HOME: tempfile.TemporaryDirectory[str] | None = None  # held for the process so the template outlives every test


def demo_template() -> Path:
    """The demo repository, built once per process: the same tree for every test, copied, never shared."""
    global _DEMO, _DEMO_HOME
    if _DEMO is None:
        _DEMO_HOME = tempfile.TemporaryDirectory()
        _DEMO = Path(_DEMO_HOME.name) / "repo"
        build_demo(_DEMO)
    return _DEMO


class KitRepository(Scratch):
    """A throwaway git repository with one bound doc, one skill, and one role.

    The base tree is built once per process and copied per test (#43, T-04);
    each test mutates and commits its own copy.
    """

    # The fixture is a bare repository, not an initialized project: skip the repository-contract checks.
    # Its files (a role, a skill, an MCP route, resources.toml) are capability carriers nothing names,
    # so the compactness gate would report every one of them; OrphanFileTests covers that gate directly.
    CONTRACT = frozenset({"manifest-structure", "skill-provenance", "file-hygiene", "markdown-links", "docs-index",
                          "orphan-files", "host-read-config"})

    def setUp(self) -> None:
        super().setUp()
        shutil.copytree(demo_template(), self.root, dirs_exist_ok=True)

    def self_heal(self) -> str:
        """The self-healing findings `make check` adds on top of the repository-contract checks."""
        hard, _ = registry.run_checks(self.root, blocking_only=True, skip=self.CONTRACT)
        return "\n".join(hard + docsync.index_errors(self.root, self.files()))

    def files(self) -> list[str]:
        return [line for line in self.git("ls-files").splitlines() if line]


def fake_gh(directory: Path, *, results: list[dict] | None = None, repo: str = "example/project",
            url: str = "https://github.com/example/project/issues/17") -> Path:
    """One `gh` stub for every test that files issues: answers, logs calls, exits loudly otherwise."""
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "gh.log"
    results_literal = json.dumps(results if results is not None else [])
    script = f"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
log = Path(os.environ.get('GH_LOG', {str(log)!r}))
if args[:2] == ['repo', 'view']:
    print(json.dumps({{'nameWithOwner': {repo!r}}}))
elif args[:2] == ['issue', 'list']:
    print({results_literal!r})
elif args[:2] == ['issue', 'create']:
    log.open('a', encoding='utf-8').write(json.dumps({{'args': args, 'stdin': sys.stdin.read()}}) + '\\n')
    print({url!r})
elif args[:2] == ['label', 'create']:
    log.open('a', encoding='utf-8').write('\\n'.join(args) + '\\n')
else:
    raise SystemExit(2)
"""
    fake = directory / "gh"
    fake.write_text(script, encoding="utf-8")
    fake.chmod(0o755)
    return log


@contextlib.contextmanager
def http_server():
    """A real HTTP answer on a port the operating system picked: nothing probed a free port first."""
    import http.server
    import threading

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *arguments: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
