"""Guided init: bounded decision intake after protective identity init (#110).

One shared question table feeds the terminal and JSON surfaces; `build_plan` is
pure (answers in, plan out, nothing written); `apply_plan` is consent-gated,
owner-hash-checked, and serialized. Identity init stays the first writer
(bootstrap.py): this module drafts pending record sections, records machine
facts in project.toml, and — only for the two vetted canonical routes — applies
the browser/Exa choice to the route owner's top-level `enabled` boolean, then
re-derives the host projection. No provider, browser, or install calls;
embeddings stay requested-not-ready; logging stays selected-intent.

The table's four optional capabilities (browser, Exa, logging, embeddings) are
strict choice strings validated at the parser boundary — no True/False coercion,
no arbitrary unknown choice. Their selected intent is recorded in the `[guided]`
receipt and a pending STACK section. For browser/Exa the owner apply then turns
an explicit `request` into `enabled = true` and an explicit `off` into
`enabled = false` in the vetted canonical route owner; `preserve` writes
nothing. The route owner's other facts (transport, url, command, env_headers)
stay opaque and untouched, and the enabled field is a real TOML boolean, never a
truthy string. A missing, malformed, symlinked, non-regular, outside-root, or
unknown route is refused before any guided write, and the plan revision binds the
entire raw route-file hash of every vetted route — preserved ones included — so
a URL/args change after the plan refuses as stale before effects. The VISION/STACK
owner-hash check repeats under the apply lock, before any write, so an owner edit
while an apply waits is refused, never overwritten. Enabling is config-only: it is
never a connection, a readiness signal, or a vendor call.

Browser/Exa default to preserve when the route is currently enabled (irrespective
of permanent new/adopt origin — a project created `new` can already ship enabled
routes) and to off when it is disabled, so a later guided init with a missing or
blank answer never switches an enabled route off; an explicit `off` still
disables. Embeddings default off (request records requested-not-ready, no
source-outbound consent); logging defaults local-redacted.

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
import stat
import time
import tomllib
from pathlib import Path

from .core import RepoctlError, ensure_inside_root, is_link_like, read_text_file
from .names import STACK_DECISION, VISION

LOCK = ".agent/guided.lock"
ENV_EXAMPLE = ".env.example"
MCP_DIR = ".agents/mcp"
SECTION = re.compile(r"(?ms)^## [ \t]*.+[ \t]*\n")

# The only canonical routes the guided owner apply may write: capability -> route
# name. Both are vetted first-party route owners (Playwright browser, Exa search);
# every other route (e.g. context7) stays route-owned and is never touched here.
_VETTED_ROUTES = {"browser": "playwright", "exa": "exa"}
# A top-level `enabled = <bool>` line in a canonical route owner.
_ENABLED_LINE = re.compile(r"(?m)^[ \t]*enabled[ \t]*=[ \t]*(?:true|false)[ \t]*$")

# The one table both surfaces read: id, prompt, options/recommendation (free-text)
# or choices/default (strict optional capabilities), and the existing record section
# the answer drafts deterministically.
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
    {"id": "browser", "prompt": "Enable the browser route (Playwright)?",
     "choices": ("off", "request", "preserve"), "default": "off",
     "recommendation": "off for a fresh template; preserve keeps an existing project's route",
     "record": STACK_DECISION, "section": "Optional capabilities"},
    {"id": "exa", "prompt": "Enable the Exa search route?",
     "choices": ("off", "request", "preserve"), "default": "off",
     "recommendation": "off for a fresh template; preserve keeps an existing project's route",
     "record": STACK_DECISION, "section": "Optional capabilities"},
    {"id": "logging", "prompt": "How should the product log?",
     "choices": ("off", "local-redacted", "plan-external"), "default": "local-redacted",
     "recommendation": "local-redacted",
     "record": STACK_DECISION, "section": "Optional capabilities"},
    {"id": "embeddings", "prompt": "Enable embeddings (vector search)?",
     "choices": ("off", "request"), "default": "off",
     "recommendation": "off",
     "record": STACK_DECISION, "section": "Optional capabilities"},
)

_QUESTION_BY_ID = {question["id"]: question for question in QUESTIONS}

# Selected intent -> recorded decision. "request" is intent, never an enabled route:
# the route files stay route-owned (SOT) until the owner apply phase.
_CHOICE_DECISIONS = {
    "browser": {"off": "off", "request": "requested", "preserve": "preserved"},
    "exa": {"off": "off", "request": "requested", "preserve": "preserved"},
    "embeddings": {"off": "not-requested", "request": "requested-not-ready"},
    "logging": {"off": "off", "local-redacted": "local-redacted", "plan-external": "plan-external"},
}


def _is_adopted(root: Path) -> bool:
    """True when the product already existed (`make adopt`); a fresh template is 'new'."""
    manifest = read_text_file(root, "project.toml") or ""
    return re.search(r'(?m)^project_mode\s*=\s*"adopt"', manifest) is not None


def _choice_default(question_id: str, adopted: bool, route_enabled: bool | None = None) -> str:
    """The known-safe default: never switch an enabled route off, whatever the project origin.

    `_is_adopted` reads a permanent `project_mode = "adopt"`, but a project created
    `new` can already ship enabled routes. So the default follows the route's CURRENT
    enabled state, not the origin: enabled -> preserve, disabled -> off. Only an
    explicit `off` disables; `preserve` always writes nothing.
    """
    if question_id in ("browser", "exa"):
        if route_enabled is True:
            return "preserve"
        if route_enabled is False:
            return "off"
        return "preserve" if adopted else "off"
    return _QUESTION_BY_ID[question_id]["default"]


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


def _mcp_projection(root: Path) -> dict[str, str]:
    """The `[guided].mcp` projection: every route's current enabled state (a derived view, never a second SOT)."""
    return {route["name"]: ("preserved" if route["enabled"] else "off-recommended")
            for route in _route_facts(root)}


def _read_route_owner(root: Path, route: str) -> tuple[bool, bytes]:
    """Read one vetted canonical route owner: (enabled bool, raw bytes).

    Refuses — before any guided write — a missing, malformed, symlinked,
    non-regular, outside-root, or misnamed route. The enabled field must be a real
    TOML boolean, never a truthy string.
    """
    path = ensure_inside_root(root, root / MCP_DIR / f"{route}.toml", f"MCP route {route} owner")
    if is_link_like(path):
        raise RepoctlError(f"MCP route {route} owner must not be a symlink or reparse point")
    if not path.is_file():
        raise RepoctlError(f"MCP route {route} owner is missing")
    raw = path.read_bytes()
    try:
        spec = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise RepoctlError(f"MCP route {route} owner is malformed: {error}") from error
    if spec.get("name") != route:
        raise RepoctlError(f"MCP route {route} owner must name itself {route!r}")
    enabled = spec.get("enabled")
    if not isinstance(enabled, bool):
        raise RepoctlError(f"MCP route {route} owner must set a real boolean enabled")
    return enabled, raw


def _vetted_route_hash(root: Path, route: str) -> str | None:
    """Raw hash of a vetted route owner for the plan revision, or None when it is absent."""
    try:
        _, raw = _read_route_owner(root, route)
    except RepoctlError:
        return None
    return _digest(raw)


def _write_enabled(path: Path, enabled: bool) -> None:
    """Flip a validated route owner's top-level `enabled` boolean, preserving comments and order."""
    text = path.read_text(encoding="utf-8")
    updated, count = _ENABLED_LINE.subn(f"enabled = {'true' if enabled else 'false'}", text, count=1)
    if count != 1:
        raise RepoctlError(f"MCP route {path.stem} owner has no top-level enabled field to set")
    path.write_text(updated, encoding="utf-8")


def _prepare_env_example(root: Path) -> Path:
    """Preflight the canonical env target before any guided write; return its path.

    The established root guard plus a regular-file check when the target is
    present: a directory, FIFO, symlink/reparse point, or broken link at the
    target is refused, never written through. Absent is fine: the writer
    creates it. No env content is read here.
    """
    path = ensure_inside_root(root, root / ENV_EXAMPLE, "env example")
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return path
    except OSError as error:
        raise RepoctlError(f"env example target is not readable: {error}") from error
    if not stat.S_ISREG(mode):
        raise RepoctlError("env example target must be a regular file, not a link, directory, or fifo")
    return path


def _prepare_route_owners(root: Path, plan: dict[str, object]) -> dict[str, bool]:
    """Validate and stale-check every vetted route the plan binds; return the needed edits.

    `request` enables, `off` disables, `preserve` writes nothing. The full raw
    route hash is the plan's binding for EVERY vetted route, preserved ones
    included, so a URL/args change after the plan was built refuses before any
    effect. Refusal happens before any guided write.
    """
    desired: dict[str, bool] = {}
    bound = plan.get("routes", {})
    for capability, route in _VETTED_ROUTES.items():
        # Missing/malformed/symlink/misnamed/outside-root refusal for every bound route.
        enabled, raw = _read_route_owner(root, route)
        if bound.get(capability) != _digest(raw):
            raise RepoctlError(f"plan is stale: .agents/mcp/{route}.toml changed after the plan was built")
        choice = plan["answers"][capability]
        if choice == "preserve":
            continue  # writes nothing, but the drift check above still applies
        want = choice == "request"
        if enabled != want:
            desired[capability] = want
    return desired


def build_plan(root: Path, answers: dict[str, str], *, consent: bool, reshape: bool = False) -> dict[str, object]:
    """Pure: answers in, plan out. Nothing is written and no record is read for writing."""
    unknown = sorted(set(answers) - {question["id"] for question in QUESTIONS})
    if unknown:
        raise RepoctlError(f"unknown intake answer(s): {', '.join(unknown)}")
    adopted = _is_adopted(root)
    enabled_by_capability = {
        capability: _read_route_owner(root, route)[0] for capability, route in _VETTED_ROUTES.items()
    }
    resolved = dict(answers)
    for question in QUESTIONS:
        if "choices" not in question:
            continue
        if question["id"] not in resolved:
            resolved[question["id"]] = _choice_default(
                question["id"], adopted, enabled_by_capability.get(question["id"]))
        elif resolved[question["id"]] not in question["choices"]:
            raise RepoctlError(
                f'answer "{question["id"]}" must be one of {"/".join(question["choices"])}, '
                f'not "{resolved[question["id"]]}"')
    records = {}
    owners = {}
    for relative in (VISION, STACK_DECISION):
        text = read_text_file(root, relative)
        if text is None:
            raise RepoctlError(f"{relative} is missing: run identity init first")
        records[relative] = "accepted" if re.search(r"(?im)^\W*status\W*:?\W*accepted\b", text) else "pending"
        owners[relative] = _digest(text.encode())
    routes = _route_facts(root)
    route_hashes = {capability: _vetted_route_hash(root, route) for capability, route in _VETTED_ROUTES.items()}
    decisions = {
        "mcp": _mcp_projection(root),
        "env": sorted({name for route in routes for name in route["env"]}),
        "browser": _CHOICE_DECISIONS["browser"][resolved["browser"]],
        "exa": _CHOICE_DECISIONS["exa"][resolved["exa"]],
        "embeddings": _CHOICE_DECISIONS["embeddings"][resolved["embeddings"]],
        "logging": _CHOICE_DECISIONS["logging"][resolved["logging"]],
    }
    plan = {"answers": resolved, "consent": bool(consent), "reshape": bool(reshape),
            "owners": owners, "records": records, "decisions": decisions, "routes": route_hashes}
    plan["revision"] = "sha256:" + hashlib.sha256(
        json.dumps({key: plan[key] for key in ("answers", "consent", "reshape", "decisions", "routes")},
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
    if not match:  # a section the skeleton does not carry yet: append it, still pending
        body = "\n\n".join(pieces)
        return text.rstrip("\n") + f"\n\n## {section}\n\n{MARK}\n{body}\n"
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


def _assert_owners_current(root: Path, plan: dict[str, object]) -> None:
    """The one owner of the authoritative VISION/STACK owner-hash check (no second copy)."""
    for relative, digest in plan["owners"].items():
        text = read_text_file(root, relative)
        if text is None or _digest(text.encode()) != digest:
            raise RepoctlError(f"plan is stale: {relative} changed after the plan was built; rebuild and reconfirm")


def apply_plan(root: Path, plan: dict[str, object]) -> list[str]:
    """Consent-gated, revision-checked apply. Any refusal writes nothing."""
    if not plan.get("consent"):
        raise RepoctlError("no explicit consent: the plan is not applied (nothing written)")
    _assert_owners_current(root, plan)  # fast refusal; the authoritative check repeats under the lock
    with _lock(root):
        return _write(root, plan)


def _write(root: Path, plan: dict[str, object]) -> list[str]:
    written: list[str] = []
    try:
        # Authoritative owner check INSIDE the lock, before any write: a VISION/STACK
        # edit while this apply waited for the lock must not be overwritten.
        _assert_owners_current(root, plan)
        # Canonical route owners first: an explicit request/off flips the top-level
        # `enabled` boolean; preserve writes nothing. Validated and stale-checked
        # before any guided write below, so a bad or changed route refuses first.
        route_edits = _prepare_route_owners(root, plan)
        # Preflight the canonical env target before any guided write when the plan
        # carries env names: the established root guard + regular-file check owns
        # the refusal, so a link/non-regular target is never written through.
        env_path = _prepare_env_example(root) if plan["decisions"]["env"] else None
        for capability, route in _VETTED_ROUTES.items():
            if capability not in route_edits:
                continue
            path = ensure_inside_root(root, root / MCP_DIR / f"{route}.toml", f"MCP route {route} owner")
            _write_enabled(path, route_edits[capability])
            written.append(path.relative_to(root).as_posix())
        if route_edits:
            plan["decisions"]["mcp"] = _mcp_projection(root)  # refresh the derived projection, no second SOT
        by_section: dict[tuple[str, str], list[str]] = {}
        for question in QUESTIONS:
            if question["id"] in plan["answers"]:
                value = plan["answers"][question["id"]]
                piece = f"{question['id']}: {value}" if "choices" in question else value
                by_section.setdefault((question["record"], question["section"]), []).append(piece)
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
        if plan["decisions"]["env"]:
            written.extend(_write_env_example(env_path, plan["decisions"]["env"]))
        manifest = (root / "project.toml").read_text(encoding="utf-8")
        (root / "project.toml").write_text(_guided_table(manifest, plan), encoding="utf-8")
        written.append("project.toml")
        if route_edits:
            # Re-derive the host projection from the canonical owners (no host MCP connect, no startup).
            from . import derive
            written.extend(derive.sync(root))
    except RepoctlError:
        raise
    except OSError as error:  # a partial failure must not look like success
        raise RepoctlError(f"guided apply stopped after {', '.join(written) or 'nothing'}: {error}") from error
    return written


def _write_env_example(env_path: Path, names: list[str]) -> list[str]:
    """Placeholder env names only: create when absent, else append missing names without overwriting values."""
    if not env_path.exists():
        lines = ["# Known environment-reference names only: fill values in your local environment;",
                 "# never commit real keys."]
        lines += [f"{name}=<set-your-own-key>" for name in names]
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return [ENV_EXAMPLE]
    existing = env_path.read_text(encoding="utf-8")
    present = set(re.findall(r"(?m)^([A-Z][A-Z0-9_]*)=", existing))
    missing = [name for name in names if name not in present]
    if not missing:
        return []
    addition = "\n".join(f"{name}=<set-your-own-key>" for name in missing)
    env_path.write_text(existing.rstrip("\n") + "\n" + addition + "\n", encoding="utf-8")
    return [ENV_EXAMPLE]


def _guided_table(manifest: str, plan: dict[str, object]) -> str:
    mcp = ", ".join(f'{name} = "{state}"' for name, state in sorted(plan["decisions"]["mcp"].items()))
    records = ", ".join(f'"{relative}:{state}"' for relative, state in sorted(plan["records"].items()))
    env = ", ".join(f'"{name}"' for name in plan["decisions"]["env"])
    table = (f"[guided]\nrevision = \"{plan['revision']}\"\nstatus = \"applied\"\nconsent = \"explicit\"\n"
             f"records = [{records}]\nmcp = {{ {mcp} }}\nenv = [{env}]\n"
             f"browser = \"{plan['decisions']['browser']}\"\nexa = \"{plan['decisions']['exa']}\"\n"
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
        question = _QUESTION_BY_ID.get(key)
        if question and "choices" in question and value not in question["choices"]:
            raise RepoctlError(
                f'answers JSON answer "{key}" must be one of {"/".join(question["choices"])}, not "{value}"')
    return payload


def ask_terminal(root: Path) -> dict[str, str] | bool | None:
    """One bounded round in the terminal: dict = answers with consent, False = no consent, None = cancelled."""
    adopted = _is_adopted(root)
    enabled_by_capability = {
        capability: _read_route_owner(root, route)[0] for capability, route in _VETTED_ROUTES.items()
    }
    print("Guided intake (#110): empty line takes the recommendation; 'cancel' writes nothing.")
    answers: dict[str, str] = {}
    for question in QUESTIONS:
        print(f"\n[{question['id']}] {question['prompt']}")
        if "choices" in question:
            print(f"  choices: {'/'.join(question['choices'])} (default: {_choice_default(question['id'], adopted, enabled_by_capability.get(question['id']))})")
        else:
            print(f"  options: {'; '.join(question['options'])}")
            print(f"  recommendation: {question['recommendation']}")
        try:
            reply = input("> ").strip()
        except EOFError:
            return None
        if reply.lower() == "cancel":
            return None
        if "choices" in question:
            answers[question["id"]] = reply or _choice_default(question["id"], adopted, enabled_by_capability.get(question["id"]))
        else:
            answers[question["id"]] = reply or question["recommendation"]
    try:
        print("\nApply this plan now? [y/N]")
        return answers if input("> ").strip().lower() in {"y", "yes"} else False
    except EOFError:
        return False


def summarize(plan: dict[str, object], applied: bool = False) -> str:
    records = ", ".join(f"{relative} {state}" for relative, state in sorted(plan["records"].items()))
    mcp = ", ".join(f"{name} {state}" for name, state in sorted(plan["decisions"]["mcp"].items())) or "no routes"
    decisions = plan["decisions"]
    # One owning fact: the capability names the user explicitly requested. An enabled
    # route is config-only — never a connection, a vendor call, or readiness — and a
    # preview must never claim "enabled".
    requested = [name for name in ("browser", "exa") if decisions[name] == "requested"]
    if applied:
        note = f"; enabled (config only): {', '.join(requested)}, connection not attempted" if requested else ""
    else:
        note = "; planned configuration only, no connection"
    return (f"revision {plan['revision'][:18]}…; {records}; MCP {mcp}; "
            f"browser {decisions['browser']}; exa {decisions['exa']}; "
            f"embeddings {decisions['embeddings']}; logging {decisions['logging']}{note}")


def guided_init(root: Path, answers: dict[str, str] | None, *, consent: bool, reshape: bool = False) -> str:
    """Intake after identity init. Returns a report; never writes without explicit consent."""
    if answers is None:
        return "No answers supplied: identity init stands; decision intake waits for product-kickoff."
    plan = build_plan(root, answers, consent=consent, reshape=reshape)
    if not consent:
        return f"Plan built, NOT applied (no explicit consent): {summarize(plan)}"
    written = apply_plan(root, plan)
    return f"Applied {summarize(plan, applied=True)}: {', '.join(written)}."
