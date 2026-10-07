"""Build trials: the kit's acceptance test, repeatable.

A navigation eval (`make eval`) asks a cold agent where things are. A build
trial asks it to build a product from an owner request and measures what the
kit did to that run: cost, turns, which commands it used, every gate block,
bypass, and Docs-Unaffected trailer, and where the product stood at the end
(`make next` phase, `make done`, completeness). Friction found here is fixed in
the kit under the blocking rule in docs/self-healing.md.

Requests live in `.agents/trials/<id>.toml`:

    id = "waypoint"
    kind = "web"                 # project kind for `make init`
    mode = "new"                 # "new": a fresh `make init` copy; "adopt": seed code first, then `make adopt`
    seed = "seeds/flask-notes"   # adopt mode: a directory under .agents/trials/ with the existing code
    budget_usd = 40              # hard spend cap for the run
    prompt = '''The owner's request, with their kickoff answers.'''

The trial copies this working tree (tracked and untracked, not ignored files),
so uncommitted kit changes are what gets tested. Reports go to the ignored
`.agent/trials/<run>/`.
"""

from __future__ import annotations

import collections
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import tomllib

from .core import RepoctlError, ensure_inside_root
from .evals import run_headless
from .gitinfo import git, listed_files

TRIALS = ".agents/trials"
REPORTS = ".agent/trials"
MODES = {"new", "adopt"}
BLOCK = re.compile(r"Commit blocked|Not finished:|check failed|Self-healing gate before stopping")
MAKE = re.compile(r"\bmake\s+([a-z][a-z0-9-]*)")


def load_trial(root: Path, identifier: str) -> dict[str, object]:
    path = ensure_inside_root(root, root / TRIALS / f"{identifier}.toml", "trial request")
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in (root / TRIALS).glob("*.toml"))) or "none"
        raise RepoctlError(f"no trial {identifier!r} in {TRIALS}/ (known: {known})")
    try:
        with path.open("rb") as handle:
            spec = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise RepoctlError(f"{path.name}: invalid TOML: {error}") from error
    for key in ("id", "kind", "prompt"):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise RepoctlError(f"{path.name}: needs a non-empty {key}")
    spec.setdefault("mode", "new")
    if spec["mode"] not in MODES:
        raise RepoctlError(f"{path.name}: mode must be one of {', '.join(sorted(MODES))}")
    if spec["mode"] == "adopt":
        seed = ensure_inside_root(root, root / TRIALS / str(spec.get("seed", "")), "trial seed")
        if not str(spec.get("seed", "")) or not seed.is_dir():
            raise RepoctlError(f"{path.name}: adopt mode needs seed = a directory under {TRIALS}/")
    return spec


def _copy(root: Path, files: list[str], target: Path) -> None:
    for relative in files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, destination)


def _run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RepoctlError(f"trial setup failed: {' '.join(command)}\n{(result.stdout + result.stderr).strip()[-600:]}")


def _commit(project: Path, message: str) -> None:
    _run(["git", "add", "-A"], project)
    _run(["git", "-c", "user.name=Trial Owner", "-c", "user.email=trial@example.invalid",
          "commit", "-q", "-m", message], project)


def prepare(root: Path, spec: dict[str, object], project: Path) -> None:
    """A fresh project as the owner would have it before asking the agent."""
    project.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q", "-b", "main"], project)
    _run(["git", "config", "user.name", "Trial Owner"], project)
    _run(["git", "config", "user.email", "trial@example.invalid"], project)
    if spec["mode"] == "new":
        _copy(root, listed_files(root), project)
        _run([sys.executable, "tools/repoctl.py", "init", "--name", str(spec["id"]), "--kind", str(spec["kind"]),
              "--owner", "trial-owner"], project)  # as the README tells a real owner to
        _commit(project, f"chore: start {spec['id']} from the template")
    else:
        seed = root / TRIALS / str(spec["seed"])
        shutil.copytree(seed, project, dirs_exist_ok=True)
        _commit(project, "existing project before the kit")
        _run([sys.executable, str(root / "tools/repoctl.py"), "--root", str(project), "adopt",
              "--from", str(root), "--name", str(spec["id"]), "--kind", str(spec["kind"]), "--owner", "trial-owner"], project)
        _commit(project, "chore: adopt the agent kit")


def host_command(spec: dict[str, object], model: str, budget: float) -> list[str]:
    return ["claude", "-p", str(spec["prompt"]), "--model", model, "--permission-mode", "bypassPermissions",
            "--max-budget-usd", f"{budget:g}", "--output-format", "stream-json", "--verbose"]


def _events(transcript: Path) -> list[dict[str, object]]:
    events = []
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _text(content: object) -> str:
    return content if isinstance(content, str) else json.dumps(content)


def analyze_transcript(transcript: Path) -> dict[str, object]:
    """Counts from a stream-json transcript: spend, tool use, kit commands, and gate friction."""
    tools: collections.Counter[str] = collections.Counter()
    targets: collections.Counter[str] = collections.Counter()
    commands: dict[str, str] = {}
    blocks, failed_make, bypasses = [], [], []
    results = []
    for event in _events(transcript):
        if event.get("type") == "result":
            results.append(event)
        content = (event.get("message") or {}).get("content") if isinstance(event.get("message"), dict) else None
        for part in content if isinstance(content, list) else []:
            if part.get("type") == "tool_use":
                tools[str(part.get("name"))] += 1
                command = str((part.get("input") or {}).get("command", ""))
                commands[str(part.get("id"))] = command
                targets.update(MAKE.findall(command))
                if "--no-verify" in command:
                    bypasses.append(" ".join(command.split())[:200])
            elif part.get("type") == "tool_result":
                command = commands.get(str(part.get("tool_use_id")), "")
                text = _text(part.get("content"))
                match = BLOCK.search(text)
                if match:
                    blocks.append({"command": " ".join(command.split())[:120], "message": " ".join(text[match.start():].split())[:400]})
                elif part.get("is_error") and MAKE.search(command):
                    failed_make.append({"command": " ".join(command.split())[:120], "message": " ".join(text.split())[-300:]})
    return {
        "cost_usd": round(sum(float(r.get("total_cost_usd") or 0) for r in results), 2),
        "turns": sum(int(r.get("num_turns") or 0) for r in results),
        "minutes": round(sum(int(r.get("duration_ms") or 0) for r in results) / 60000, 1),
        "completed": bool(results) and results[-1].get("subtype") == "success",
        "tools": dict(tools.most_common()),
        "make_targets": dict(targets.most_common()),
        "gate_blocks": blocks,
        "failed_make": failed_make,
        "bypasses": bypasses,
        "final_message": str(results[-1].get("result", "")) if results else "",
    }


def project_state(project: Path) -> dict[str, object]:
    """Where the product stands, read with the project's own kit."""
    def repoctl(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "tools/repoctl.py", *arguments], cwd=project,
                              capture_output=True, text=True, check=False, timeout=1800)
    trailers = git(project, "log", "--format=%(trailers:key=Docs-Unaffected,valueonly)") or ""
    finish = repoctl("finish")
    summary = [line for line in finish.stdout.splitlines() if line.startswith(("Product ", "UI review"))]
    return {
        "commits": len((git(project, "rev-list", "HEAD") or "").split()),
        "next": (repoctl("next").stdout.splitlines() or [""])[0],
        "finish_passed": finish.returncode == 0,
        "finish": summary or (finish.stdout.strip().splitlines() or [""])[-3:],
        "trailers": [line for line in trailers.splitlines() if line.strip()],
    }


def render(spec: dict[str, object], model: str, analysis: dict[str, object], state: dict[str, object], project: Path) -> str:
    lines = [
        f"# Build trial: {spec['id']} ({spec['mode']}, {model})", "",
        f"Project: `{project}`", "",
        f"- Spend: ${analysis['cost_usd']} over {analysis['turns']} turns, {analysis['minutes']} min; "
        f"completed: {analysis['completed']}",
        f"- Commits: {state['commits']}; `make done` passed: {state['finish_passed']}",
        f"- Final `make next`: {state['next']}",
        *(f"- {line}" for line in state["finish"]),
        f"- Kit commands: {', '.join(f'{k}×{v}' for k, v in analysis['make_targets'].items()) or 'none'}",
        "", "## Friction", "",
        f"- Gate blocks: {len(analysis['gate_blocks'])}",
        *(f"  - after `{b['command']}`: {b['message']}" for b in analysis["gate_blocks"]),
        f"- Failed kit commands: {len(analysis['failed_make'])}",
        *(f"  - `{f['command']}`: {f['message']}" for f in analysis["failed_make"]),
        f"- `--no-verify` bypasses: {len(analysis['bypasses'])}",
        *(f"  - `{b}`" for b in analysis["bypasses"]),
        f"- Docs-Unaffected trailers: {len(state['trailers'])}",
        *(f"  - {t}" for t in state["trailers"]),
        "", "Judge each item with docs/self-healing.md#when-a-check-may-block: fix the kit, "
        "make it advisory, or justify the block.", "",
        "## Final message", "", analysis["final_message"].strip() or "(none)", "",
    ]
    return "\n".join(lines)


def run_trial(root: Path, identifier: str, model: str = "sonnet", budget: float | None = None,
              directory: str | None = None, timeout: int = 7200) -> int:
    spec = load_trial(root, identifier)
    if shutil.which("claude") is None:
        raise RepoctlError("build trials need the claude CLI (other hosts: run the prompt by hand, then --analyze)")
    budget = float(budget if budget is not None else spec.get("budget_usd", 25))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = root / REPORTS / f"{stamp}-{identifier}"
    report_dir.mkdir(parents=True, exist_ok=True)
    # Outside this repository: agents load ancestor CLAUDE.md files, which would leak this kit's context.
    project = Path(directory).resolve() if directory else Path(tempfile.mkdtemp(prefix=f"trial-{identifier}-")) / identifier
    prepare(root, spec, project)
    print(f"Trial {identifier}: project at {project}; transcript in {report_dir.relative_to(root)}/ (up to ${budget:g})")
    transcript = report_dir / "transcript.jsonl"
    started = time.monotonic()
    print(f"If this runner is interrupted, report later with: tools/repoctl trial {identifier} "
          f"--analyze {transcript.relative_to(root)} --project {project}")
    with transcript.open("w", encoding="utf-8") as output:
        try:
            run_headless(host_command(spec, model, budget), project, timeout, stdout=output)
        except subprocess.TimeoutExpired:
            print(f"trial stopped after {timeout}s")
    print(f"agent finished in {(time.monotonic() - started) / 60:.0f} min; analyzing")
    return write_report(root, spec, model, transcript, project, report_dir)


def write_report(root: Path, spec: dict[str, object], model: str, transcript: Path, project: Path, report_dir: Path) -> int:
    analysis = analyze_transcript(transcript)
    try:
        state = project_state(project)
    except subprocess.TimeoutExpired as error:
        state = {"commits": 0, "next": f"(project state timed out after {error.timeout:g}s)", "finish_passed": False,
                 "finish": ["project state timed out: re-run the report with --analyze"], "trailers": []}
    (report_dir / "report.json").write_text(json.dumps({"spec": spec, "model": model, "project": str(project),
                                                        "analysis": analysis, "state": state}, indent=2) + "\n")
    report = render(spec, model, analysis, state, project)
    (report_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"report: {(report_dir / 'report.md').relative_to(root)}")
    return 0


def analyze_existing(root: Path, identifier: str, transcript: str, project: str, model: str = "sonnet") -> int:
    """Report on a run made by hand (another host, or a rerun of the analysis)."""
    spec = load_trial(root, identifier)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_dir = root / REPORTS / f"{stamp}-{identifier}"
    report_dir.mkdir(parents=True, exist_ok=True)
    return write_report(root, spec, model, Path(transcript).resolve(), Path(project).resolve(), report_dir)
