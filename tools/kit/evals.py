"""Fresh-agent benchmark: can a cold agent navigate this repository?

Tasks live in `.agents/evals/*.toml`. Each run launches a headless agent host
in read-only mode, checks the answer against an expected regex, and records
pass rate, turns, duration, and cost (when the host reports them) under the
ignored `.agent/evals/`. Compare runs before and after changing the kit.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import tomllib  # repoctl.py fails fast on Python < 3.11

from .config import setting
from .core import RepoctlError
from .gitinfo import run_git

READ_ONLY_TOOLS = "Read Grep Glob Bash(make where:*) Bash(make map) Bash(git log:*) Bash(git status)"
# The agent under test must not read its own answer key (.agents/evals/**), so the
# claude command denies reads of it. Deny rules win over allow rules.
EVAL_KEY = ".agents/evals"
DENIED_READS = [f"{tool}({pattern})" for tool in ("Read", "Grep", "Glob") for pattern in (f"{EVAL_KEY}/**", f"**/{EVAL_KEY}/**")]
HOST_COMMANDS = {
    # Navigation needs no MCP servers; an empty strict config keeps runs fast and deterministic.
    "claude": lambda prompt, model: [
        "claude", "-p", prompt, "--output-format", "json", "--strict-mcp-config",
        "--mcp-config", '{"mcpServers": {}}', *(["--model", model] if model else []),
        "--allowedTools", *READ_ONLY_TOOLS.split(" "),
        "--disallowedTools", *DENIED_READS,
    ],
    "codex": lambda prompt, model: ["codex", "exec", "--sandbox", "read-only", *(["--model", model] if model else []), prompt],
    "gemini": lambda prompt, model: ["gemini", *(["--model", model] if model else []), "-p", prompt],
}
# A fresh agent must not inherit the launching session: host session variables
# would route a nested CLI through the parent's (short-lived) session auth.
INHERITED_SESSION = (
    "CLAUDECODE", "CLAUDE_CODE_", "CLAUDE_PID", "CLAUDE_AGENT_SDK", "CLAUDE_EFFORT", "CLAUDE_PREVIEW", "ANTHROPIC_BASE_URL",
)
HOST_BINARIES = {"claude": "claude", "codex": "codex", "gemini": "gemini"}
PREFIX = "You are a fresh agent in this repository. Do not edit files. Answer briefly. Task: "


def run_headless(command: list[str], cwd: Path, timeout: int, stdout=None) -> subprocess.CompletedProcess[str]:
    """Run a fresh headless agent: the one launcher behind make eval and make trial.

    It drops the launching session's host variables (so the CLI uses its own login,
    as a truly fresh agent would), allows bypassed permissions when running as root
    in a sandbox, and shields itself from SIGTERM while the agent runs: agents clean up with
    `pkill -f <name>`, which also matches the runner's command line (a trial killed
    its own runner that way). On timeout (or interrupt) it SIGKILLs the whole process group, then raises
    subprocess.TimeoutExpired like subprocess.run.
    """
    environment = {key: value for key, value in os.environ.items() if not key.startswith(INHERITED_SESSION)}
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        environment.setdefault("IS_SANDBOX", "1")  # the CLI refuses bypassed permissions as root outside a sandbox
    # A no-op handler (not SIG_IGN): exec resets handlers to default, so the agent's own
    # children keep default SIGTERM handling, while this runner still survives `pkill -f`.
    previous = signal.signal(signal.SIGTERM, lambda *_: None) if hasattr(signal, "SIGTERM") else None
    streams = {"stdout": stdout, "stderr": subprocess.STDOUT} if stdout else {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    try:
        process = subprocess.Popen(command, cwd=cwd, env=environment, text=True, start_new_session=True, **streams)
        try:
            out, err = process.communicate(timeout=timeout)
        except BaseException:
            kill_group(process)
            process.communicate()
            raise
        kill_group(process)  # nothing the agent backgrounded outlives the run
        return subprocess.CompletedProcess(command, process.returncode, out, err)
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def kill_group(process: subprocess.Popen) -> None:
    """SIGKILL the run's whole process group (it leads its own session)."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, AttributeError):
        pass


def load_tasks(root: Path, only: str | None = None) -> list[dict[str, str]]:
    tasks = []
    for suite in sorted((root / ".agents" / "evals").glob("*.toml")):
        try:
            with suite.open("rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as error:
            raise RepoctlError(f"{suite.name}: invalid TOML: {error}") from error
        for task in data.get("tasks", []):
            if not all(isinstance(task.get(key), str) and task[key] for key in ("id", "prompt", "expect")):
                raise RepoctlError(f"{suite.name}: every task needs id, prompt, and expect")
            try:
                re.compile(task["expect"])
            except re.error as error:
                raise RepoctlError(f"{suite.name}: task {task['id']} has an invalid expect regex: {error}") from error
            if only is None or task["id"] in only.split(","):
                tasks.append(task)
    if only is not None:
        unknown = [name for name in only.split(",") if name not in {task["id"] for task in tasks}]
        if unknown:
            raise RepoctlError(f"unknown eval task id(s): {', '.join(unknown)}")
    return tasks


def answer_matches(task: dict[str, str], answer: str) -> bool:
    return bool(re.search(task["expect"], answer, re.IGNORECASE))


def run_task(root: Path, host: str, task: dict[str, str], timeout: int, model: str = "") -> dict[str, object]:
    command = HOST_COMMANDS[host](PREFIX + task["prompt"], model)
    started = time.monotonic()
    try:
        result = run_headless(command, root, timeout)
        output = result.stdout
    except subprocess.TimeoutExpired:
        return {"id": task["id"], "passed": False, "error": f"timeout after {timeout}s"}
    record: dict[str, object] = {"id": task["id"], "seconds": round(time.monotonic() - started, 1)}
    answer = output
    if host == "claude":
        try:
            data = json.loads(output)
            answer = str(data.get("result", ""))
            record.update(turns=data.get("num_turns"), cost_usd=data.get("total_cost_usd"))
            if data.get("is_error"):
                return {**record, "passed": False, "error": answer[:300]}
        except json.JSONDecodeError:
            pass
    record["passed"] = answer_matches(task, answer)
    record["answer"] = " ".join(answer.split())[:240]
    if result.returncode != 0 and not record["passed"]:
        record["error"] = (result.stderr or "").strip()[-300:]
    return record


@contextmanager
def committed_checkout(root: Path):
    """A clean, detached worktree of HEAD for the agents under test, removed afterwards.

    A cold agent must meet the committed repository, not this checkout's uncommitted
    edits, its hook state, or the stop-gate findings they raise: a live run once
    answered a stop-hook finding about an unrelated uncommitted file instead of the
    question. Outside a git repository, the checkout itself is used.
    """
    with tempfile.TemporaryDirectory(prefix="kit-eval-") as temp:
        target = Path(temp) / "repo"
        added = run_git(root, "worktree", "add", "--detach", "--quiet", str(target), "HEAD", timeout=120)
        if added is None or added.returncode != 0:
            yield root
            return
        try:
            yield target
        finally:
            run_git(root, "worktree", "remove", "--force", str(target), timeout=120)


def run_evals(root: Path, host: str, only: str | None = None, timeout: int = 300, model: str | None = None) -> int:
    if host not in HOST_COMMANDS:
        raise RepoctlError(f"unsupported eval host {host}; choose {', '.join(HOST_COMMANDS)}")
    if model is None:
        model = str(setting(root, "eval_model")) if host == "claude" else ""
    if shutil.which(HOST_BINARIES[host]) is None:
        raise RepoctlError(f"{host} CLI is not installed")
    tasks = load_tasks(root, only)
    if not tasks:
        raise RepoctlError("no eval tasks selected")
    records = []
    with committed_checkout(root) as checkout:
        for task in tasks:
            record = run_task(checkout, host, task, timeout, model)
            records.append(record)
            mark = "PASS" if record["passed"] else "FAIL"
            extras = " ".join(f"{key}={record[key]}" for key in ("seconds", "turns", "cost_usd") if record.get(key) is not None)
            print(f"{mark} {task['id']} {extras}\n     {record.get('answer') or record.get('error', '')}", flush=True)
    passed = sum(1 for record in records if record["passed"])
    cost = sum(float(record.get("cost_usd") or 0) for record in records)
    print(f"\n{passed}/{len(records)} passed" + (f" with {model}" if model else "") + (f", total cost ${cost:.4f}" if cost else ""))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / ".agent" / "evals" / f"{stamp}-{host}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"host": host, "model": model, "records": records}, indent=2) + "\n", encoding="utf-8")
    print(f"recorded {target.relative_to(root).as_posix()}")
    return 0 if passed == len(records) else 1
