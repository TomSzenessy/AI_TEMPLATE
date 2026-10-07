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
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError as error:  # pragma: no cover - exercised on Python 3.10
    raise SystemExit("repoctl requires Python 3.11 or newer") from error

from .config import setting
from .core import RepoctlError

READ_ONLY_TOOLS = "Read Grep Glob Bash(make where:*) Bash(make map) Bash(git log:*) Bash(git status)"
HOST_COMMANDS = {
    # Navigation needs no MCP servers; an empty strict config keeps runs fast and deterministic.
    "claude": lambda prompt, model: [
        "claude", "-p", prompt, "--output-format", "json", "--strict-mcp-config",
        "--mcp-config", '{"mcpServers": {}}', *(["--model", model] if model else []),
        "--allowedTools", *READ_ONLY_TOOLS.split(" "),
    ],
    "codex": lambda prompt, model: ["codex", "exec", "--sandbox", "read-only", *(["--model", model] if model else []), prompt],
    "gemini": lambda prompt, model: ["gemini", *(["--model", model] if model else []), "-p", prompt],
}
# A fresh agent must not inherit the launching session: host session variables
# would route a nested CLI through the parent's (short-lived) session auth.
INHERITED_SESSION = ("CLAUDECODE", "CLAUDE_CODE_", "CLAUDE_PID", "CLAUDE_AGENT_SDK", "CLAUDE_EFFORT", "CLAUDE_PREVIEW", "ANTHROPIC_BASE_URL")
PREFIX = "You are a fresh agent in this repository. Do not edit files. Answer briefly. Task: "


def run_headless(command: list[str], cwd: Path, timeout: int, stdout=None) -> subprocess.CompletedProcess[str]:
    """Run a fresh headless agent: the one launcher behind make eval and make trial.

    It drops the launching session's host variables (so the CLI uses its own login,
    as a truly fresh agent would), allows bypassed permissions when running as root
    in a sandbox, and ignores SIGTERM while the agent runs: agents clean up with
    `pkill -f <name>`, which also matches the runner's command line (a trial killed
    its own runner that way). Raises subprocess.TimeoutExpired like subprocess.run.
    """
    environment = {key: value for key, value in os.environ.items() if not key.startswith(INHERITED_SESSION)}
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        environment.setdefault("IS_SANDBOX", "1")  # the CLI refuses bypassed permissions as root outside a sandbox
    previous = signal.signal(signal.SIGTERM, signal.SIG_IGN) if hasattr(signal, "SIGTERM") else None
    try:
        return subprocess.run(command, cwd=cwd, env=environment, text=True, timeout=timeout, check=False,
                              start_new_session=True, **({"stdout": stdout, "stderr": subprocess.STDOUT} if stdout
                                                         else {"capture_output": True}))
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)


def load_tasks(root: Path, only: str | None = None) -> list[dict[str, str]]:
    tasks = []
    for suite in sorted((root / ".agents" / "evals").glob("*.toml")):
        with suite.open("rb") as handle:
            data = tomllib.load(handle)
        for task in data.get("tasks", []):
            if not all(isinstance(task.get(key), str) and task[key] for key in ("id", "prompt", "expect")):
                raise RepoctlError(f"{suite.name}: every task needs id, prompt, and expect")
            re.compile(task["expect"])
            if only is None or task["id"] in only.split(","):
                tasks.append(task)
    return tasks


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
    record["passed"] = bool(re.search(task["expect"], answer, re.IGNORECASE))
    record["answer"] = " ".join(answer.split())[:240]
    if result.returncode != 0 and not record["passed"]:
        record["error"] = (result.stderr or "").strip()[-300:]
    return record


def run_evals(root: Path, host: str, only: str | None = None, timeout: int = 300, model: str | None = None) -> int:
    if host not in HOST_COMMANDS:
        raise RepoctlError(f"unsupported eval host {host}; choose {', '.join(HOST_COMMANDS)}")
    if model is None:
        model = str(setting(root, "eval_model")) if host == "claude" else ""
    if shutil.which(HOST_COMMANDS[host]("x", "")[0]) is None:
        raise RepoctlError(f"{host} CLI is not installed")
    tasks = load_tasks(root, only)
    if not tasks:
        raise RepoctlError("no eval tasks selected")
    records = []
    for task in tasks:
        record = run_task(root, host, task, timeout, model)
        records.append(record)
        mark = "PASS" if record["passed"] else "FAIL"
        extras = " ".join(f"{key}={record[key]}" for key in ("seconds", "turns", "cost_usd") if record.get(key) is not None)
        print(f"{mark} {task['id']} {extras}\n     {record.get('answer') or record.get('error', '')}")
    passed = sum(1 for record in records if record["passed"])
    cost = sum(float(record.get("cost_usd") or 0) for record in records)
    print(f"\n{passed}/{len(records)} passed" + (f" with {model}" if model else "") + (f", total cost ${cost:.4f}" if cost else ""))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / ".agent" / "evals" / f"{stamp}-{host}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"host": host, "model": model, "records": records}, indent=2) + "\n", encoding="utf-8")
    print(f"recorded {target.relative_to(root).as_posix()}")
    return 0 if passed == len(records) else 1
