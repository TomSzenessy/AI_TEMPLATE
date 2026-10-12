"""Guided init: bounded decision intake after protective identity init (#110).

One shared question table feeds the terminal and JSON surfaces; `build_plan` is
pure (answers in, plan out, nothing written); `apply_plan` is consent-gated,
owner-hash-checked, and serialized. Identity init stays the first writer
(bootstrap.py): this module only drafts pending record sections, records machine
facts in project.toml, and reads — never writes — the MCP route owners. No
provider, browser, or install calls; embeddings stay requested-not-ready.

`consent` and `reshape` are the module's only switches, so `answers_from_json`
validates them as real JSON booleans before any guided write: a typed string
such as `"false"` is rejected, never coerced — Python truthiness would read any
non-empty string as explicit consent and apply the plan (#110).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import time
import tomllib
from pathlib import Path

from .core import RepoctlError, ensure_inside_root, read_text_file
from .names import STACK_DECISION, VISION

LOCK = ".agent/guided.lock"
ENV_EXAMPLE = ".env.example"
MCP_DIR = ".agents/mcp"
SECTION = re.compile(r"(?ms)^## [ \t]*.+[ \t]*\n")

# The one table both surfaces read: id, prompt, options, recommendation, and the
# existing record section the answer drafts deterministically.
QUESTIONS = (
    {"id": "users_goal", "prompt": "Who is it for, which problem, and what success looks like?",
     "options": ("one sentence, one success metric",), "recommendation": "See product-kickoff question 1",
     "record": VISION, "section": "Outcome"},
    {"id": "success_metric", "prompt": "How will we know it works (the one metric)?",
     "options": ("a usage, correctness, or business metric",), "recommendation": "judge the product by one metric",
     "record": VISION, "section": "Success evidence"},
    {"id": "platforms", "prompt": "Which platforms, and is offline needed?",
     "options": ("web", "ios", "android", "desktop", "offline"),
     "recommendation": "web; add platforms only when users need them",
     "record": VISION, "section": "Platforms and constraints"},
    {"id": "constraints", "prompt": "Budget, deadline, hosting, must-use services, privacy limits?",
     "options": ("one line each, or 'none beyond the template gates'",),
     "recommendation": "none beyond the template gates",
     "record": VISION, "section": "Platforms and constraints"},
    {"id": "stack", "prompt": "Language, framework, data store, hosting (pinned versions)?",
     "options": ("an existing codebase wins", "React + Next.js + Tailwind for web"),
     "recommendation": "React + Next.js + Tailwind for web",
     "record": STACK_DECISION, "section": "Decision"},
    {"id": "stack_alternatives", "prompt": "What else was considered, and why did it lose?",
     "options": ("one alternative and its downside",), "recommendation": "SvelteKit: smaller ecosystem for this team",
     "record": STACK_DECISION, "section": "Why this, and what else was considered"},
    {"id": "stack_verification", "prompt": "Which commands prove it works, and how do we back out?",
     "options": ("make check and make verify",), "recommendation": "make check and make verify; git revert rolls back",
     "record": STACK_DECISION, "section": "Verification and rollback"},
)


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _route_facts(root: Path) -> list[dict[str, object]]:
    """Current route-owned MCP state and env-reference names; route files are only read."""
    facts = []
    for path in sorted((root / MCP_DIR).glob("*.toml")):
        spec = tomllib.loads(path.read_text(encoding="utf-8"))
        facts.append({"name": spec.get("name", path.stem), "enabled": bool(spec.get("enabled", False)),
                      "env": sorted(set(spec.get("env_headers", {}).values()))})
    return facts


def build_plan(root: Path, answers: dict[str, str], *, consent: bool, reshape: bool = False) -> dict[str, object]:
    """Pure: answers in, plan out. Nothing is written and no record is read for writing."""
    unknown = sorted(set(answers) - {question["id"] for question in QUESTIONS})
    if unknown:
        raise RepoctlError(f"unknown intake answer(s): {', '.join(unknown)}")
    records = {}
    owners = {}
    for relative in (VISION, STACK_DECISION):
        text = read_text_file(root, relative)
        if text is None:
            raise RepoctlError(f"{relative} is missing: run identity init first")
        records[relative] = "accepted" if re.search(r"(?im)^\W*status\W*:?\W*accepted\b", text) else "pending"
        owners[relative] = _digest(text.encode())
    routes = _route_facts(root)
    decisions = {
        "mcp": {route["name"]: ("preserved" if route["enabled"] else "off-recommended") for route in routes},
        "env": sorted({name for route in routes for name in route["env"]}),
        "embeddings": "requested-not-ready",
        "logging": "local-redacted",
    }
    plan = {"answers": dict(answers), "consent": bool(consent), "reshape": bool(reshape),
            "owners": owners, "records": records, "decisions": decisions}
    plan["revision"] = "sha256:" + hashlib.sha256(
        json.dumps({key: plan[key] for key in ("answers", "consent", "reshape", "decisions")},
                   sort_keys=True).encode()).hexdigest()
    return plan


MARK = "<!-- guided-intake -->"  # names a drafted paragraph so a later reshape replaces, never duplicates, it


def _draft(text: str, section: str, pieces: list[str]) -> str:
    """Draft answers under `## section`: replace the placeholder or a previous guided draft, else append."""
    pieces = [piece.strip() for piece in pieces if piece and piece.strip()]
    if not pieces:
        return text
    heading = re.compile(r"(?ms)^## " + re.escape(section) + r"[ \t]*\n")
    match = heading.search(text)
    if not match:
        return text
    found = SECTION.search(text, match.end())
    end = found.start() if found else len(text)
    block = text[match.end():end]
    body = "\n\n".join(pieces)
    if body in block:
        return text  # already drafted: a second apply changes nothing
    paragraphs = block.split("\n\n")
    for index, paragraph in enumerate(paragraphs):
        stripped = paragraph.strip()
        if stripped.startswith(MARK) or stripped.startswith("[REQUIRED:"):
            paragraphs[index] = f"{MARK}\n{body}"
            break
    else:
        paragraphs.append(f"{MARK}\n{body}")
    replacement = "\n\n".join(part for part in paragraphs if part.strip())
    return text[:match.end()] + replacement + "\n\n" + text[end:]


@contextlib.contextmanager
def _lock(root: Path, timeout: float = 10):
    """Serialize cooperating apply callers; a stuck lock times out instead of hanging."""
    path = root / LOCK
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() > deadline:
                raise RepoctlError(f"another guided apply holds {LOCK}; retry once it is done")
            time.sleep(0.05)
        else:
            break
    try:
        os.write(handle, str(os.getpid()).encode())
        yield
    finally:
        os.close(handle)
        path.unlink(missing_ok=True)


def apply_plan(root: Path, plan: dict[str, object]) -> list[str]:
    """Consent-gated, revision-checked apply. Any refusal writes nothing."""
    if not plan.get("consent"):
        raise RepoctlError("no explicit consent: the plan is not applied (nothing written)")
    for relative, digest in plan["owners"].items():
        text = read_text_file(root, relative)
        if text is None or _digest(text.encode()) != digest:
            raise RepoctlError(f"plan is stale: {relative} changed after the plan was built; rebuild and reconfirm")
    with _lock(root):
        return _write(root, plan)


def _write(root: Path, plan: dict[str, object]) -> list[str]:
    written: list[str] = []
    try:
        by_section: dict[tuple[str, str], list[str]] = {}
        for question in QUESTIONS:
            if question["id"] in plan["answers"]:
                by_section.setdefault((question["record"], question["section"]), []).append(plan["answers"][question["id"]])
        for (relative, section), pieces in by_section.items():
            if plan["records"][relative] == "accepted" and not plan["reshape"]:
                continue  # an accepted record is preserved unless an explicit reshape is supplied
            text = read_text_file(root, relative) or ""
            drafted = _draft(text, section, pieces)
            if drafted != text:
                path = ensure_inside_root(root, root / relative, "intake record")
                path.write_text(drafted, encoding="utf-8")
                if relative not in written:
                    written.append(relative)
        env_path = root / ENV_EXAMPLE
        if plan["decisions"]["env"] and not env_path.exists():  # placeholder names only, never values
            lines = ["# Known environment-reference names only: fill values in your local environment;",
                     "# never commit real keys."]
            lines += [f"{name}=<set-your-own-key>" for name in plan["decisions"]["env"]]
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            written.append(ENV_EXAMPLE)
        manifest = (root / "project.toml").read_text(encoding="utf-8")
        (root / "project.toml").write_text(_guided_table(manifest, plan), encoding="utf-8")
        written.append("project.toml")
    except RepoctlError:
        raise
    except OSError as error:  # a partial failure must not look like success
        raise RepoctlError(f"guided apply stopped after {', '.join(written) or 'nothing'}: {error}") from error
    return written


def _guided_table(manifest: str, plan: dict[str, object]) -> str:
    mcp = ", ".join(f'{name} = "{state}"' for name, state in sorted(plan["decisions"]["mcp"].items()))
    records = ", ".join(f'"{relative}:{state}"' for relative, state in sorted(plan["records"].items()))
    env = ", ".join(f'"{name}"' for name in plan["decisions"]["env"])
    table = (f"[guided]\nrevision = \"{plan['revision']}\"\nstatus = \"applied\"\nconsent = \"explicit\"\n"
             f"records = [{records}]\nmcp = {{ {mcp} }}\nenv = [{env}]\n"
             f"embeddings = \"{plan['decisions']['embeddings']}\"\nlogging = \"{plan['decisions']['logging']}\"\n")
    updated, count = re.subn(r"(?ms)^\[guided\]\s*.*?(?=^\[|\Z)", table, manifest, count=1)
    return updated if count else manifest.rstrip("\n") + "\n\n" + table


def answers_from_json(text: str) -> dict[str, object]:
    """The shared JSON intake schema, validated before any guided write.

    `consent`/`reshape` must be real JSON booleans: a typed string like `"false"`
    is a refusal, not a value to coerce — Python truthiness would read any
    non-empty string as explicit consent and apply the plan (#110). `answers`
    values must be strings. Raises RepoctlError on the first violation.
    """
    try:
        payload = json.loads(text)
    except ValueError as error:
        raise RepoctlError(f"answers are not valid JSON: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("answers"), dict):
        raise RepoctlError('answers JSON needs {"consent": bool, "answers": {question id: text}}')
    for key in ("consent", "reshape"):
        if key in payload and not isinstance(payload[key], bool):
            raise RepoctlError(
                f'answers JSON "{key}" must be a JSON boolean true/false, not a typed string or number')
    for key, value in payload["answers"].items():
        if not isinstance(value, str):
            raise RepoctlError(f'answers JSON answer "{key}" must be a string')
    return payload


def ask_terminal() -> dict[str, str] | bool | None:
    """One bounded round in the terminal: dict = answers with consent, False = no consent, None = cancelled."""
    print("Guided intake (#110): empty line takes the recommendation; 'cancel' writes nothing.")
    answers: dict[str, str] = {}
    for question in QUESTIONS:
        print(f"\n[{question['id']}] {question['prompt']}")
        print(f"  options: {'; '.join(question['options'])}")
        print(f"  recommendation: {question['recommendation']}")
        try:
            reply = input("> ").strip()
        except EOFError:
            return None
        if reply.lower() == "cancel":
            return None
        answers[question["id"]] = reply or question["recommendation"]
    try:
        print("\nApply this plan now? [y/N]")
        return answers if input("> ").strip().lower() in {"y", "yes"} else False
    except EOFError:
        return False


def summarize(plan: dict[str, object]) -> str:
    records = ", ".join(f"{relative} {state}" for relative, state in sorted(plan["records"].items()))
    mcp = ", ".join(f"{name} {state}" for name, state in sorted(plan["decisions"]["mcp"].items())) or "no routes"
    return (f"revision {plan['revision'][:18]}…; {records}; MCP {mcp}; embeddings requested-not-ready; "
            "logging local-redacted")


def guided_init(root: Path, answers: dict[str, str] | None, *, consent: bool, reshape: bool = False) -> str:
    """Intake after identity init. Returns a report; never writes without explicit consent."""
    if answers is None:
        return "No answers supplied: identity init stands; decision intake waits for product-kickoff."
    plan = build_plan(root, answers, consent=consent, reshape=reshape)
    if not consent:
        return f"Plan built, NOT applied (no explicit consent): {summarize(plan)}"
    return f"Applied {summarize(plan)}: {', '.join(apply_plan(root, plan))}."
