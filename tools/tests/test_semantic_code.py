"""Optional consent-gated semantic code similarity for `make similar --code` (#115).

No test contacts a real embedding provider and no test sends private code
anywhere: the transport is a first-party fake adapter, HTTP fixtures are local
trusted servers, and every refusal path is asserted to make zero outbound
calls. The default capability-only behavior of `make similar` is asserted
unchanged alongside the new code results.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import KitRepository, Scratch, git_in  # noqa: E402

from kit import semantic  # noqa: E402
from kit.navigate import _tokens  # noqa: E402  the lexical convention the fake mirrors

KEY_ENV = "SEMANTIC_API_KEY"
KEY_VALUE = "fixture-key-not-real"  # a fixture value only; never a real key
ENDPOINT = "https://embeddings.example.test/v1"
MODEL = "fixture-embedding-model"


def _synthetic_secret() -> str:
    """A credential-looking literal the hygiene scanner must still flag, assembled at
    runtime so this tracked source never holds a static secret-shaped token."""
    return "-".join(("synthetic", "fixture", "secret", "01"))


def _pem_fixture() -> str:
    """A PEM-shaped key fixture assembled at runtime: the tracked source holds no static
    private-key literal, while the filename-based exclusion still sees a key file."""
    label = "RSA PRIVATE KEY"
    return f"-----BEGIN {label}-----\nfixture\n-----END {label}-----\n"


def enable(root: Path, **overrides) -> None:
    """A [kit] table that switches the optional semantic path on for this fixture.

    Idempotent: calling with updates modifies the existing [kit] section instead of
    appending a duplicate (which would make project.toml invalid TOML).
    """
    values = {"semantic_enabled": True, "semantic_endpoint": ENDPOINT, "semantic_model": MODEL}
    values.update(overrides)
    path = root / "project.toml"
    text = path.read_text(encoding="utf-8")
    if "[kit]" in text:
        lines = text.splitlines()
        in_kit = False
        seen: set[str] = set()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                in_kit = (stripped == "[kit]")
                continue
            if in_kit and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in values:
                    lines[i] = f"{key} = {json.dumps(values[key])}"
                    seen.add(key)
        new_lines = [f"{key} = {json.dumps(value)}" for key, value in values.items() if key not in seen]
        if new_lines:
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]") and stripped != "[kit]" and i > 0:
                    lines[i:i] = new_lines
                    break
            else:
                lines.extend(new_lines)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        lines = ["", "[kit]"]
        for key, value in values.items():
            lines.append(f"{key} = {json.dumps(value)}")
        path.write_text(text + "\n".join(lines) + "\n", encoding="utf-8")


class FakeTransport:
    """A first-party fake embedding adapter: deterministic vectors, recorded calls, scripted failures."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail is not None:
            raise self.fail
        return [_vector(text) for text in texts]


def _vector(text: str) -> list[float]:
    """Deterministic bag-of-words vector: shared tokens with the query score higher."""
    vector = [0.0] * 8
    for token in _tokens(text):
        vector[hash(token) % 8] += 1.0
    return vector


def run_with_fake(test: KitRepository, fake: FakeTransport, *arguments: str, stdin: str | None = None):
    """Run the CLI with the fake adapter standing in for the configured transport."""
    with mock.patch.object(semantic, "configured_transport", return_value=fake):
        return test.cli(*arguments, stdin=stdin, env={KEY_ENV: KEY_VALUE})


class SemanticConsentTests(KitRepository):
    """Consent is the boundary: no confirmation, no outbound — key presence is not consent."""

    def build(self, stdin: str | None = "y\n") -> None:
        result = run_with_fake(self, FakeTransport(), "similar", "--code-index", stdin=stdin)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("index built", result.stdout)

    def test_disabled_by_default_makes_no_outbound_call(self) -> None:
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", "Q=render invoices", "--code")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("disabled", result.stdout)
        self.assertEqual(fake.calls, [], "disabled semantic search must not reach the transport")

    def test_key_presence_is_not_consent(self) -> None:
        enable(self.root)
        self.build()  # an index must exist before consent is prompted
        # Remove stored consent: key presence alone must not grant outbound
        (self.root / ".agent" / "semantic-code-consent.json").unlink(missing_ok=True)
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", "Q=render invoices", "--code")  # empty stdin: no confirmation
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no consent", result.stdout)
        self.assertEqual(fake.calls, [], "a stored key is not consent; nothing may be sent")

    def test_confirmed_consent_sends_the_query(self) -> None:
        enable(self.root)
        self.build()  # an index must exist before the query is embedded
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", "Q=render invoice", "--code", stdin="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(fake.calls), 1, "exactly one outbound request after confirmation")
        self.assertEqual(fake.calls[0], ["render invoice"], "only the query text is sent, never code on this path")
        self.assertIn("code:", result.stdout)

    def test_consent_flag_confirms_without_a_prompt(self) -> None:
        enable(self.root)
        self.build()  # an index must exist before the query is embedded
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", "Q=render invoice", "--code", "--consent")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(fake.calls), 1, "the explicit user flag confirms the scope without a prompt")
        self.assertIn("code:", result.stdout)

    def test_stored_consent_survives_a_prompt_free_rerun(self) -> None:
        enable(self.root)
        self.build()  # an index must exist before the query is embedded
        fake = FakeTransport()
        first = run_with_fake(self, fake, "similar", "Q=render invoice", "--code", stdin="y\n")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = run_with_fake(self, fake, "similar", "Q=render invoice", "--code")  # no stdin: would decline
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(len(fake.calls), 2, "a matching stored confirmation must not re-prompt or re-block")

    def test_changed_policy_invalidates_stored_consent(self) -> None:
        enable(self.root)
        self.build()
        fake = FakeTransport()
        enable(self.root, semantic_model="another-fixture-model")  # changed policy: new scope
        declined = run_with_fake(self, fake, "similar", "Q=render invoice", "--code")
        self.assertIn("model changed", declined.stdout)
        self.assertEqual(len(fake.calls), 0, "the changed scope was never sent")

    def test_secret_query_is_never_sent(self) -> None:
        enable(self.root)
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", f'Q="api_key = "{_synthetic_secret()}"', "--code", "--consent")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("key material", result.stdout)
        self.assertEqual(fake.calls, [], "a query that may hold key material is refused, not sent")


class SemanticInventoryTests(KitRepository):
    """Eligible code inventory: git-tracked textual code only, every exclusion honored."""

    def inventory(self) -> dict:
        return semantic.inventory(self.root, semantic._config(self.root))

    def test_tracked_code_file_is_eligible(self) -> None:
        paths = [f.split(":")[0] for f in self.inventory()["files"]]
        self.assertIn("src/billing/invoice.py", paths)

    def test_untracked_file_is_excluded_by_default(self) -> None:
        self.write("src/billing/new_module.py", "def new_module():\n    return 2\n")
        self.assertNotIn("src/billing/new_module.py", self.inventory()["files"])

    def test_gitignored_and_generated_trees_are_excluded(self) -> None:
        self.write("build/generated.py", "def generated():\n    return 3\n")
        self.write("node_modules/dep/index.js", "function dep() { return 4 }\n")
        self.write("vendor/lib.py", "def vendor():\n    return 5\n")
        self.write("dist/bundle.js", "function bundle() { return 6 }\n")
        self.write("__pycache__/cached.pyc", "\x00\x01binary-ish\x00")
        files = self.inventory()["files"]
        for relative in ("build/generated.py", "node_modules/dep/index.js", "vendor/lib.py",
                         "dist/bundle.js", "__pycache__/cached.pyc"):
            self.assertNotIn(relative, files)

    def test_agent_claude_review_prefixes_are_excluded(self) -> None:
        self.write(".claude/settings.json", "{}\n")
        self.write(".agents/rules/house.md", "# House\n")
        self.write(".agents/skills/demo-skill/SKILL.md", "---\nname: demo-skill\ndescription: x\n---\n")
        self.write(".agents/mcp/browser.toml", "name = \"browser\"\n")
        self.write(".review/findings.md", "# Findings\n")
        self.git("add", "-A")  # truly tracked before asserting exclusion
        files = self.inventory()["files"]
        for relative in (".claude/settings.json", ".agents/rules/house.md",
                         ".agents/skills/demo-skill/SKILL.md", ".agents/mcp/browser.toml",
                         ".review/findings.md"):
            self.assertNotIn(relative, files)

    def test_env_and_key_files_are_excluded(self) -> None:
        self.write(".env", "API_KEY=fixture\n")
        self.write(".env.example", "API_KEY=<set-your-own-key>\n")
        self.write("deploy/id_rsa", _pem_fixture())
        self.write("certs/server.pem", "-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n")
        files = self.inventory()["files"]
        for relative in (".env", ".env.example", "deploy/id_rsa", "certs/server.pem"):
            self.assertNotIn(relative, files)

    def test_secret_flagged_content_is_excluded(self) -> None:
        self.write("src/billing/leak.py", f'api_key = "{_synthetic_secret()}"\n')
        self.assertNotIn("src/billing/leak.py", self.inventory()["files"])

    def test_symlink_escaping_the_root_is_excluded(self) -> None:
        outside = self.root.parent / "semantic-escape-fixture.py"
        outside.write_text("def escape():\n    return 7\n", encoding="utf-8")
        self.addCleanup(outside.unlink)
        (self.root / "src" / "billing" / "escape.py").symlink_to(outside)
        self.git("add", "-A")
        self.assertNotIn("src/billing/escape.py", self.inventory()["files"])

    def test_non_code_text_is_excluded(self) -> None:
        self.write("notes/invoice.md", "# Invoice notes\n")
        self.write("data/invoice.json", "{}\n")
        files = self.inventory()["files"]
        self.assertNotIn("notes/invoice.md", files)
        self.assertNotIn("data/invoice.json", files)

    def test_file_and_chunk_budgets_are_enforced(self) -> None:
        for number in range(5):
            self.write(f"src/bulk/module{number}.py", f"def module{number}():\n    return {number}\n")
        self.git("add", "-A")  # truly tracked before asserting budgets
        config = dict(semantic._config(self.root))
        config["max_files"] = 2
        config["max_file_bytes"] = 30
        inventory = semantic.inventory(self.root, config)
        self.assertEqual(len(inventory["files"]), 2, "the file budget caps the inventory")
        self.assertEqual(inventory["skipped"].get("over file byte budget"), 3, "small files still fit the byte budget")


class SemanticCacheTests(KitRepository):
    """The cache holds vectors and hashes only; every change invalidates it."""

    def setUp(self) -> None:
        super().setUp()
        enable(self.root)
        self.fake = FakeTransport()

    def build(self, stdin: str | None = "y\n") -> None:
        result = run_with_fake(self, self.fake, "similar", "--code-index", stdin=stdin)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("index built", result.stdout)

    def cache_path(self) -> Path:
        return self.root / ".agent" / "semantic-code-cache.json"

    def test_cache_stores_vectors_and_hashes_but_no_code_or_keys(self) -> None:
        self.build()
        raw = json.loads(self.cache_path().read_text(encoding="utf-8"))
        self.assertEqual(raw["schema_version"], semantic.SCHEMA_VERSION)
        self.assertEqual(raw["model"], MODEL)
        self.assertEqual(raw["endpoint"], ENDPOINT)
        text = json.dumps(raw)
        self.assertNotIn("def render_invoice", text, "the cache never holds raw code")
        self.assertNotIn(KEY_VALUE, text, "the cache never holds keys")
        for entry in raw["files"]:
            self.assertIn("sha256", entry)
            for chunk in entry["chunks"]:
                self.assertIn("vector", chunk)
                self.assertIn("sha256", chunk)
                self.assertNotIn("text", chunk)

    def test_content_change_invalidates_and_requires_reconsent(self) -> None:
        self.build()
        calls = len(self.fake.calls)
        run_with_fake(self, self.fake, "similar", "Q=render invoice", "--code")  # valid index: query only
        self.assertEqual(len(self.fake.calls), calls + 1, "a valid index serves the query without re-indexing")
        self.write("src/billing/invoice.py", "def render_invoice():\n    return 11\n")
        stale = run_with_fake(self, self.fake, "similar", "Q=render invoice", "--code")
        self.assertIn("changed since indexing", stale.stdout)
        self.assertEqual(len(self.fake.calls), calls + 1, "a stale index is never used and never re-sent")
        self.build()  # explicit --code-index re-consents (scope changed) and rebuilds
        self.assertEqual(len(self.fake.calls), calls + 2, "the explicit index operation re-indexes the new content")

    def test_model_change_invalidates_the_index(self) -> None:
        self.build()
        enable(self.root, semantic_model="another-fixture-model")
        result = run_with_fake(self, self.fake, "similar", "Q=render invoice", "--code")
        self.assertIn("model changed", result.stdout)
        self.assertIn("lexical code matches", result.stdout, "a stale index returns no semantic result")

    def test_scope_change_invalidates_the_index(self) -> None:
        self.build()
        self.write("src/billing/extra.py", "def extra():\n    return 8\n")
        self.git("add", "-A")
        result = run_with_fake(self, self.fake, "similar", "Q=render invoice", "--code")
        self.assertIn("changed since indexing", result.stdout)

    def test_root_change_invalidates_the_index(self) -> None:
        self.build()
        # Copy the working tree (including .agent cache/consent) to a new location,
        # then set up an independent git repo with the SAME origin and branch.
        # The physical path differs, so the root binding must refuse consent/cache.
        import shutil
        clone_root = self.root.parent / "semantic-clone-fixture"
        self.addCleanup(shutil.rmtree, clone_root, True)
        clone_root.mkdir(parents=True, exist_ok=True)
        for item in self.root.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.copytree(item, clone_root / item.name, dirs_exist_ok=True)
            else:
                shutil.copy2(item, clone_root / item.name)
        clone = Scratch()
        clone.root = clone_root
        clone.git("init", "-q", "-b", "main")
        clone.git("config", "user.email", "test@example.com")
        clone.git("config", "user.name", "Test")
        remote_result = self.git_result("remote", "get-url", "origin")
        if remote_result.returncode == 0:
            clone.git("remote", "add", "origin", remote_result.stdout.strip())
        clone.git("add", "-A")
        clone.git("commit", "-q", "-m", "clone")
        clone.write("project.toml", (self.root / "project.toml").read_text(encoding="utf-8"))
        fake = FakeTransport()
        with mock.patch.object(semantic, "configured_transport", return_value=fake):
            result = clone.cli("similar", "Q=render invoice", "--code", env={KEY_ENV: KEY_VALUE})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("root changed", result.stdout)
        self.assertEqual(fake.calls, [], "a different physical root must refuse consent: zero outbound")
        with mock.patch.object(semantic, "configured_transport", return_value=fake):
            status = clone.cli("similar", "--code-status", env={KEY_ENV: KEY_VALUE})
        self.assertIn("consent: none", status.stdout)
        self.assertIn("index: stale", status.stdout)

    def test_failed_index_build_keeps_the_last_valid_cache(self) -> None:
        self.build()
        before = self.cache_path().read_text(encoding="utf-8")
        failing = FakeTransport(fail=semantic.SemanticError("embedding request failed: timeout"))
        result = run_with_fake(self, failing, "similar", "--code-index", stdin="y\n")
        self.assertIn("index build failed", result.stdout)
        self.assertEqual(self.cache_path().read_text(encoding="utf-8"), before, "a failed build must not clobber the cache")


class SemanticTransportValidationTests(unittest.TestCase):
    """Strict embedding response validation: partial success is not complete."""

    def validate(self, payload, input_count):
        return semantic.validated_embeddings(payload, input_count)

    def test_accepts_a_well_formed_response(self) -> None:
        payload = {"data": [{"index": 0, "embedding": [0.1, 0.2]}, {"index": 1, "embedding": [0.3, 0.4]}]}
        self.assertEqual(self.validate(payload, 2), [[0.1, 0.2], [0.3, 0.4]])

    def test_rejects_input_count_mismatch(self) -> None:
        payload = {"data": [{"index": 0, "embedding": [0.1]}]}
        with self.assertRaises(semantic.SemanticError):
            self.validate(payload, 2)

    def test_rejects_duplicate_indices(self) -> None:
        payload = {"data": [{"index": 0, "embedding": [0.1]}, {"index": 0, "embedding": [0.2]}]}
        with self.assertRaises(semantic.SemanticError):
            self.validate(payload, 2)

    def test_rejects_mixed_dimensions(self) -> None:
        payload = {"data": [{"index": 0, "embedding": [0.1, 0.2]}, {"index": 1, "embedding": [0.3]}]}
        with self.assertRaises(semantic.SemanticError):
            self.validate(payload, 2)

    def test_rejects_non_finite_and_non_numeric_values(self) -> None:
        for bad in ([0.1, float("nan")], [0.1, float("inf")], [0.1, "0.2"]):
            payload = {"data": [{"index": 0, "embedding": bad}, {"index": 1, "embedding": [0.3, 0.4]}]}
            with self.assertRaises(semantic.SemanticError):
                self.validate(payload, 2)

    def test_rejects_an_all_zero_vector(self) -> None:
        payload = {"data": [{"index": 0, "embedding": [0.0, 0.0]}, {"index": 1, "embedding": [0.3, 0.4]}]}
        with self.assertRaises(semantic.SemanticError):
            self.validate(payload, 2)

    def test_partial_success_is_not_complete(self) -> None:
        payload = {"data": [{"index": 0, "embedding": [0.1, 0.2]}, {"index": 1, "embedding": [0.0, 0.0]}]}
        with self.assertRaises(semantic.SemanticError):
            self.validate(payload, 2)


class _LocalEmbeddingServer:
    """A local trusted HTTP fixture: records requests, answers from a script, never leaves the machine."""

    def __init__(self, handler) -> None:
        self.requests: list[tuple[dict, bytes]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - the http.server hook name
                length = int(self.headers.get("Content-Length", "0"))
                outer.requests.append((dict(self.headers), self.rfile.read(length)))
                status, body = handler(outer.requests[-1][1])
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *arguments) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class SemanticTransportTests(KitRepository):
    """The OpenAI-compatible transport over the standard library only."""

    def transport_config(self, endpoint: str) -> dict:
        config = dict(semantic._config(self.root))
        config["endpoint"] = endpoint
        config["timeout"] = 5
        config["model"] = MODEL
        return config

    def test_sends_openai_compatible_request_with_the_key_redacted_from_failures(self) -> None:
        server = _LocalEmbeddingServer(lambda body: (
            200, json.dumps({"data": [{"index": 0, "embedding": [0.1, 0.2]}, {"index": 1, "embedding": [0.3, 0.4]}]}).encode()
        ))
        self.addCleanup(server.close)
        transport = semantic.OpenAITransport(server.url, KEY_VALUE, self.transport_config(server.url))
        self.assertEqual(transport.embed(["render invoice", "other text"]), [[0.1, 0.2], [0.3, 0.4]])
        headers, body = server.requests[0]
        self.assertEqual(headers.get("Authorization"), f"Bearer {KEY_VALUE}")
        payload = json.loads(body)
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["input"], ["render invoice", "other text"])
        # A failure message must not leak the key.
        failing = _LocalEmbeddingServer(lambda body: (500, b""))
        self.addCleanup(failing.close)
        cfg = self.transport_config(failing.url)
        cfg["retries"] = 0
        redacted = semantic.OpenAITransport(failing.url, KEY_VALUE, cfg)
        with self.assertRaises(semantic.SemanticError) as caught:
            redacted.embed(["render invoice"])
        self.assertNotIn(KEY_VALUE, str(caught.exception))

    def test_redirect_is_never_followed(self) -> None:
        server = _LocalEmbeddingServer(lambda body: (302, b""))
        self.addCleanup(server.close)
        transport = semantic.OpenAITransport(server.url, KEY_VALUE, self.transport_config(server.url))
        with self.assertRaises(semantic.SemanticError):
            transport.embed(["render invoice"])

    def test_malformed_count_falls_back_honestly(self) -> None:
        server = _LocalEmbeddingServer(lambda body: (200, json.dumps({"data": [{"index": 0, "embedding": [0.1]}]}).encode()))
        self.addCleanup(server.close)
        transport = semantic.OpenAITransport(server.url, KEY_VALUE, self.transport_config(server.url))
        with self.assertRaises(semantic.SemanticError):
            transport.embed(["render invoice", "other text"])


class SemanticFallbackTests(KitRepository):
    """Every failure is an honest lexical fallback, never a silent one."""

    def build(self, stdin: str | None = "y\n") -> None:
        result = run_with_fake(self, FakeTransport(), "similar", "--code-index", stdin=stdin)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("index built", result.stdout)

    def fallback(self, fake: FakeTransport, query: str = "render invoice", *, build: bool = True) -> str:
        enable(self.root)
        if build:
            self.build()
        result = run_with_fake(self, fake, "similar", f"Q={query}", "--code", stdin="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_timeout_falls_back_with_an_honest_reason(self) -> None:
        failing = FakeTransport(fail=semantic.SemanticError("embedding request failed: timeout"))
        output = self.fallback(failing)
        self.assertIn("timeout", output)
        self.assertIn("lexical code matches", output)
        self.assertIn("code:src/billing/invoice.py", output)

    def test_invalid_response_falls_back_with_an_honest_reason(self) -> None:
        failing = FakeTransport(fail=semantic.SemanticError("embedding count 1 != input count 2"))
        output = self.fallback(failing)
        self.assertIn("count", output)
        self.assertIn("lexical code matches", output)

    def test_missing_index_reports_how_to_build_it(self) -> None:
        fake = FakeTransport()
        output = self.fallback(fake, build=False)
        self.assertIn("--code-index", output)
        self.assertEqual(fake.calls, [], "without a valid index nothing is sent")

    def test_new_repository_falls_back_with_an_honest_reason(self) -> None:
        fresh = Scratch()
        fresh.setUp()
        fresh.git("init", "-q", "-b", "main")
        fresh.write("project.toml", "schema = 1\nname = \"Fresh\"\nkind = \"web\"\n")
        enable(fresh.root)
        fake = FakeTransport()
        result = run_with_fake(fresh, fake, "similar", "Q=render invoice", "--code")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no tracked files", result.stdout)
        self.assertEqual(fake.calls, [], "a repository with no commits sends nothing")


class SimilarCodeTests(KitRepository):
    """The extended CLI: default lexical preserved, code results added, status local."""

    def test_default_output_is_unchanged(self) -> None:
        result = self.cli("similar", "Q=render invoices for customers")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skill:demo-skill", result.stdout)
        self.assertIn("Verdict:", result.stdout)
        self.assertNotIn("code:", result.stdout, "the capability-only path must not grow a code section")
        self.assertNotIn("semantic", result.stdout)

    def test_code_results_alongside_the_unchanged_verdict(self) -> None:
        enable(self.root)
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", "Q=render invoice", "--code", stdin="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skill:demo-skill", result.stdout)
        self.assertIn("Verdict:", result.stdout)
        self.assertIn("code:src/billing/invoice.py:1-2:", result.stdout)
        self.assertRegex(result.stdout, r"0\.\d\d  code:src/billing/invoice\.py:1-2:")

    def test_code_status_makes_no_outbound_call(self) -> None:
        enable(self.root)
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", "--code-status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("semantic code search: enabled", result.stdout)
        self.assertIn("fixture-embedding-model", result.stdout)
        self.assertEqual(fake.calls, [], "status is local only")

    def test_code_index_builds_the_index(self) -> None:
        enable(self.root)
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", "--code-index", stdin="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("index built", result.stdout)
        self.assertTrue((self.root / ".agent" / "semantic-code-cache.json").is_file())

    def test_code_index_without_consent_builds_nothing(self) -> None:
        enable(self.root)
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", "--code-index")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no consent", result.stdout)
        self.assertFalse((self.root / ".agent" / "semantic-code-cache.json").exists())

    def test_similarity_never_deletes_code(self) -> None:
        enable(self.root)
        before = (self.root / "src" / "billing" / "invoice.py").read_text(encoding="utf-8")
        run_with_fake(self, FakeTransport(), "similar", "Q=render invoice", "--code", stdin="y\n")
        run_with_fake(self, FakeTransport(), "similar", "--code-index", stdin="y\n")
        self.assertEqual((self.root / "src" / "billing" / "invoice.py").read_text(encoding="utf-8"), before)

    def test_blank_query_makes_no_outbound_call(self) -> None:
        enable(self.root)
        fake = FakeTransport()
        result = run_with_fake(self, fake, "similar", "Q=", "--code", stdin="y\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no query", result.stdout)
        self.assertEqual(fake.calls, [], "a blank query must not reach the transport")


class SemanticInvalidEndpointTests(KitRepository):
    """An unsafe configured endpoint degrades honestly instead of raising (#115 critic)."""

    def test_non_https_endpoint_falls_back_to_lexical_with_a_reason(self) -> None:
        for endpoint in ("http://plain.example.test/v1", "https://user:pw@creds.example.test/v1",
                         "https://query.example.test/v1?k=v"):
            with self.subTest(endpoint=endpoint):
                enable(self.root, semantic_endpoint=endpoint)
                with mock.patch.dict(os.environ, {KEY_ENV: KEY_VALUE}):
                    matches, reasons = semantic.code_matches(self.root, "render invoice")
                    summary = semantic.build_index(self.root, consent=True)
                self.assertTrue(reasons, "the fallback must say why")
                self.assertNotIn("pw", " ".join(reasons + summary), "credentials are never echoed")
                self.assertTrue(any("index not built" in line for line in summary), summary)
                self.assertFalse((self.root / ".agent" / "semantic-code-cache.json").exists())
                status = "\n".join(semantic.status_lines(self.root))
                self.assertIn("(invalid:", status)
                self.assertNotIn("pw@", status, "status never echoes a credentialed endpoint")


class SemanticSnapshotTests(unittest.TestCase):
    """Approved-snapshot invariant (#115): a supplied cfg is used exactly; _config is never re-read."""

    def test_configured_transport_uses_the_supplied_cfg_without_a_reread(self) -> None:
        approved = {
            "api_key_env": KEY_ENV,
            "endpoint": "https://approved-snapshot.example.test/v1",
            "model": "approved-snapshot-model",
        }
        with mock.patch.object(semantic, "_config", side_effect=AssertionError("_config must not be re-read once a cfg is supplied")):
            with mock.patch.dict(os.environ, {KEY_ENV: KEY_VALUE}):
                transport = semantic.configured_transport(Path("/unused"), config=approved)
        self.assertIs(transport.config, approved, "NoTuple A→B: the transport must use the exact approved cfg object")
        self.assertEqual(transport.config["model"], "approved-snapshot-model")
        self.assertEqual(transport.url, "https://approved-snapshot.example.test/v1/embeddings")
        self.assertEqual(transport.key, KEY_VALUE, "only the known safe TEST-marker key is used")


class SemanticEnvResolverTests(unittest.TestCase):
    """The safe env resolver: private .env, bounded read, plain data only.

    Every test uses its own controlled temp Root with a fake .env; the actual
    repository Root.env is never read. No test contacts a provider or sends
    anything outbound: the only transport is an injected first-party fake —
    no HTTP, no real credentials. The inventory-scope proofs below likewise
    use a controlled temp git root, never the repository's own tree.
    """

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)

    def write_env(self, text: str) -> None:
        (self.root / ".env").write_text(text, encoding="utf-8")

    def test_private_dotenv_parses_quotes_comments_export_blank_alias_and_duplicate(self) -> None:
        secret = _synthetic_secret()  # runtime-built; the tracked source holds no static secret
        self.write_env(
            "# a comment line\n"
            "export TEST_EXPORT=exported-value\n"
            'TEST_QUOTED="quoted # not comment"\n'
            "TEST_INLINE=inline-value # trailing comment\n"
            "TEST_BLANK=\n"
            f"TEST_SECRET={secret}\n"
            "TEST_DUP=first\n"
            "TEST_DUP=second\n"
            "UNRELATED=ignored\n"
        )
        names = frozenset({"TEST_EXPORT", "TEST_QUOTED", "TEST_INLINE", "TEST_BLANK", "TEST_SECRET", "TEST_DUP"})
        found = semantic._read_dotenv(self.root, names)
        self.assertEqual(found["TEST_EXPORT"], "exported-value")
        self.assertEqual(found["TEST_QUOTED"], "quoted # not comment", "# inside quotes is literal")
        self.assertEqual(found["TEST_INLINE"], "inline-value", "an inline # comment outside quotes is stripped")
        self.assertEqual(found["TEST_BLANK"], "")
        self.assertEqual(found["TEST_SECRET"], secret)
        self.assertNotIn("TEST_DUP", found, "a duplicate binding is dropped as ambiguous")
        self.assertNotIn("UNRELATED", found, "only requested names are read")
        # A symlink alias for .env is rejected before any read.
        (self.root / ".env").unlink()
        outside = self.root.parent / "semantic-env-alias-fixture"
        outside.write_text("TEST_EXPORT=alias\n", encoding="utf-8")
        self.addCleanup(outside.unlink)
        (self.root / ".env").symlink_to(outside)
        self.assertEqual(semantic._read_dotenv(self.root, frozenset({"TEST_EXPORT"})), {}, "a symlink alias is rejected")

    def test_dotenv_over_64kib_is_rejected_with_a_bounded_read(self) -> None:
        # A valid binding, then padding that pushes the REAL file over the 64 KiB bound.
        self.write_env("TEST_A=alpha\n" + "#" + "x" * semantic._ENV_MAX_BYTES + "\n")
        read_sizes: list[int] = []
        real_open = Path.open

        def recording_open(self, mode="r", *args, **kwargs):
            handle = real_open(self, mode, *args, **kwargs)
            if "b" not in mode:
                return handle

            class _Recorder:
                def __init__(self, inner):
                    self._inner = inner

                def read(self, size=-1):
                    read_sizes.append(size)
                    return self._inner.read(size)

                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return self._inner.__exit__(*exc)

            return _Recorder(handle)

        # stat claims the file is small; the real content is over the bound. The bounded
        # binary read (_ENV_MAX_BYTES + 1) is what catches it — not the stat check.
        fake_stat = mock.Mock()
        fake_stat.st_mode = stat.S_IFREG | 0o644
        fake_stat.st_size = 100
        with mock.patch.object(Path, "open", recording_open):
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("unbounded read_text must not be used")):
                with mock.patch.object(Path, "stat", return_value=fake_stat):
                    found = semantic._read_dotenv(self.root, frozenset({"TEST_A"}))
        self.assertEqual(found, {}, "an over-limit .env is rejected even when stat claims under")
        self.assertIn(semantic._ENV_MAX_BYTES + 1, read_sizes, "the bounded binary read API is used")


    def test_model_env_change_is_a_scope_mismatch_and_not_ready_is_never_sent(self) -> None:
        """ENV model/endpoint change is a scope/cache mismatch: zero outbound, lexical fallback.

        In-process proof only (no CLI, no subprocess): build an index bound to
        MODEL_A/ENDPOINT_A, mutate the ENV to B, then verify code_matches/build_index
        refuse with lexical fallback BEFORE any outbound request (FakeTransport.calls == 0),
        consent/cache fingerprints (endpoint+model) actually changed, and no credential
        leaks into output/cfg/cache/consent JSON.
        """
        model_a = "fixture-model-a"
        endpoint_a = "https://fixture-a.example.test/v1"
        key_fake = _synthetic_secret()  # runtime-built; the tracked source holds no static secret
        model_b = "fixture-model-b"
        endpoint_b = "https://fixture-b.example.test/v1"
        # A controlled git repo: only project.toml and src are tracked, never .env.
        git_in(self.root, "init", "-q", "-b", "main")
        git_in(self.root, "config", "user.email", "test@example.com")
        git_in(self.root, "config", "user.name", "Test")
        (self.root / "src").mkdir(parents=True, exist_ok=True)
        (self.root / "src" / "invoice.py").write_text("def render_invoice():\n    return 1\n", encoding="utf-8")
        (self.root / "project.toml").write_text('schema = 1\nname = "Fixture"\nkind = "web"\n', encoding="utf-8")
        git_in(self.root, "add", "project.toml", "src")
        git_in(self.root, "commit", "-q", "-m", "initial")
        enable(self.root, semantic_endpoint="env:EMBEDDINGS_ENDPOINT", semantic_model="env:EMBEDDINGS_MODEL")
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in ("EMBEDDINGS_MODEL", "EMBEDDINGS_ENDPOINT", "EMBEDDINGS_API_KEY"):
                os.environ.pop(name, None)  # clear actual EmbVars; real Root.env never read
            # --- Build the index bound to MODEL_A/ENDPOINT_A (injected fake, no CLI) ---
            self.write_env(f"EMBEDDINGS_MODEL={model_a}\nEMBEDDINGS_ENDPOINT={endpoint_a}\nEMBEDDINGS_API_KEY={key_fake}\n")
            fake_a = FakeTransport()
            summary = semantic.build_index(self.root, transport=fake_a, consent=True)
            self.assertIn("index built", "\n".join(summary))
            self.assertIn(model_a, "\n".join(summary))
            self.assertIn(endpoint_a, "\n".join(summary))
            # Cache and consent are bound to MODEL_A/ENDPOINT_A.
            cache = json.loads((self.root / ".agent" / "semantic-code-cache.json").read_text(encoding="utf-8"))
            consent = json.loads((self.root / ".agent" / "semantic-code-consent.json").read_text(encoding="utf-8"))
            self.assertEqual(cache["model"], model_a)
            self.assertEqual(cache["endpoint"], endpoint_a)
            self.assertEqual(consent["model"], model_a)
            self.assertEqual(consent["endpoint"], endpoint_a)
            config_a = semantic._config(self.root)
            digest_a = semantic.scope_digest(config_a, semantic.inventory(self.root, config_a))
            # --- Mutate MODEL/ENDPOINT env to B: stale cache, lexical fallback, ZERO outbound ---
            self.write_env(f"EMBEDDINGS_MODEL={model_b}\nEMBEDDINGS_ENDPOINT={endpoint_b}\nEMBEDDINGS_API_KEY={key_fake}\n")
            fake_b = FakeTransport()
            matches, reasons = semantic.code_matches(self.root, "render invoice", transport=fake_b)
            self.assertTrue(matches, "lexical matches must be available without a valid index")
            self.assertTrue(any("model changed" in reason or "endpoint changed" in reason for reason in reasons),
                            f"expected a model/endpoint change reason, got: {reasons}")
            self.assertEqual(fake_b.calls, [], "zero outbound after env model/endpoint change")
            # build_index: stored consent no longer matches → no consent (EOF on stdin), ZERO outbound.
            fake_c = FakeTransport()
            with mock.patch("builtins.input", side_effect=EOFError):
                refused = semantic.build_index(self.root, transport=fake_c)
            self.assertTrue(any("no consent" in line for line in refused), f"expected no-consent refusal, got: {refused}")
            self.assertEqual(fake_c.calls, [], "zero outbound on rebuild after env change")
            # No credential leakage into output or any .agent JSON; cfg stores model/endpoint only.
            output = "\n".join(summary + reasons + refused)
            self.assertNotIn(key_fake, output, "the key value must never appear in output")
            for json_file in (self.root / ".agent").glob("*.json"):
                self.assertNotIn(key_fake, json_file.read_text(encoding="utf-8"),
                                f"API key leaked into {json_file.name}")
            self.assertNotIn(key_fake, json.dumps(config_a), "cfg stores model/endpoint, never the key value")
            self.assertEqual(config_a["model"], model_a)
            self.assertEqual(config_a["endpoint"], endpoint_a)
            # Consent/cache fingerprints (endpoint+model) actually changed — not str alone.
            config_b = semantic._config(self.root)
            digest_b = semantic.scope_digest(config_b, semantic.inventory(self.root, config_b))
            self.assertNotEqual(digest_a, digest_b, "scope digest must change with model/endpoint")

    def test_eligible_path_replacement_same_count_invalidates_consent(self) -> None:
        """Same file count, new eligible path → new scope: re-prompt, zero outbound.

        In-process proof only (no CLI, no subprocess): build an index bound to
        the original paths, rename one eligible file (SAME count), then verify
        the scope digest changed, code_matches refuses with an invalid cache
        (FakeTransport.calls == 0), build_index with EOF stdin refuses BEFORE
        the transport, the stored consent is untouched until an explicit
        re-confirmation, and that re-confirmation re-indexes with real fake
        calls. A path change is a new consent scope, not a content edit.
        """
        git_in(self.root, "init", "-q", "-b", "main")
        git_in(self.root, "config", "user.email", "test@example.com")
        git_in(self.root, "config", "user.name", "Test")
        (self.root / "src").mkdir(parents=True, exist_ok=True)
        (self.root / "src" / "alpha.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
        (self.root / "src" / "beta.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
        (self.root / "project.toml").write_text('schema = 1\nname = "Fixture"\nkind = "web"\n', encoding="utf-8")
        git_in(self.root, "add", "project.toml", "src")
        git_in(self.root, "commit", "-q", "-m", "initial")
        enable(self.root)
        fake_a = FakeTransport()
        summary = semantic.build_index(self.root, transport=fake_a, consent=True)
        self.assertIn("index built", "\n".join(summary))
        config = semantic._config(self.root)
        snapshot_a = semantic.inventory(self.root, config)
        digest_a = semantic.scope_digest(config, snapshot_a)
        consent_path = self.root / ".agent" / "semantic-code-consent.json"
        consent_a = json.loads(consent_path.read_text(encoding="utf-8"))
        self.assertEqual(consent_a["scope_digest"], digest_a)
        # Rename: SAME eligible file count, NEW eligible path.
        git_in(self.root, "mv", "src/alpha.py", "src/renamed_alpha.py")
        git_in(self.root, "commit", "-q", "-m", "rename alpha")
        snapshot_b = semantic.inventory(self.root, config)
        self.assertEqual(len(snapshot_b["files"]), len(snapshot_a["files"]), "same file count")
        self.assertNotEqual([item.split(":", 1)[0] for item in snapshot_b["files"]],
                            [item.split(":", 1)[0] for item in snapshot_a["files"]], "new eligible path")
        digest_b = semantic.scope_digest(config, snapshot_b)
        self.assertNotEqual(digest_b, digest_a, "a renamed eligible file must start a new consent scope")
        # code_matches: the rename makes the cache stale → lexical fallback, ZERO outbound.
        fake_b = FakeTransport()
        matches, reasons = semantic.code_matches(self.root, "alpha", transport=fake_b)
        self.assertTrue(matches, "lexical matches must be available without a valid index")
        self.assertTrue(any("changed since indexing" in reason for reason in reasons),
                        f"expected an invalid-cache reason, got: {reasons}")
        self.assertEqual(fake_b.calls, [], "zero outbound with an invalid cache after a rename")
        # build_index with EOF stdin: refused BEFORE the transport; consent A untouched.
        fake_c = FakeTransport()
        with mock.patch("builtins.input", side_effect=EOFError):
            refused = semantic.build_index(self.root, transport=fake_c)
        self.assertTrue(any("no consent" in line for line in refused), f"expected no-consent refusal, got: {refused}")
        self.assertEqual(fake_c.calls, [], "zero outbound on refused rebuild after a rename")
        self.assertEqual(json.loads(consent_path.read_text(encoding="utf-8")), consent_a,
                         "stored consent A is untouched until B is explicitly approved")
        # Explicit re-confirmation of B: positive fake calls, record now bound to B.
        fake_d = FakeTransport()
        rebuilt = semantic.build_index(self.root, transport=fake_d, consent=True)
        self.assertIn("index built", "\n".join(rebuilt))
        self.assertGreater(len(fake_d.calls), 0, "explicit re-confirmation re-indexes")
        consent_b = json.loads(consent_path.read_text(encoding="utf-8"))
        self.assertEqual(consent_b["scope_digest"], digest_b, "the approved record is bound to the new scope")

    def test_new_file_and_chunk_count_change_invalidate_consent(self) -> None:
        """New eligible path or changed chunk count → new scope; a same-path,
        same-chunk-count code edit keeps the stored consent (vectors only stale).
        """
        git_in(self.root, "init", "-q", "-b", "main")
        git_in(self.root, "config", "user.email", "test@example.com")
        git_in(self.root, "config", "user.name", "Test")
        (self.root / "src").mkdir(parents=True, exist_ok=True)
        (self.root / "src" / "alpha.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
        (self.root / "src" / "beta.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
        (self.root / "project.toml").write_text('schema = 1\nname = "Fixture"\nkind = "web"\n', encoding="utf-8")
        git_in(self.root, "add", "project.toml", "src")
        git_in(self.root, "commit", "-q", "-m", "initial")
        enable(self.root)
        fake_a = FakeTransport()
        summary = semantic.build_index(self.root, transport=fake_a, consent=True)
        self.assertIn("index built", "\n".join(summary))
        config = semantic._config(self.root)
        consent_path = self.root / ".agent" / "semantic-code-consent.json"
        consent_a = json.loads(consent_path.read_text(encoding="utf-8"))
        digest_a = semantic.scope_digest(config, semantic.inventory(self.root, config))
        # Case 1 (control): same path set, same chunk count → consent kept, vectors stale only.
        (self.root / "src" / "alpha.py").write_text("def alpha():\n    return 11\n", encoding="utf-8")
        git_in(self.root, "add", "-A")
        git_in(self.root, "commit", "-q", "-m", "edit alpha")
        snapshot_e = semantic.inventory(self.root, config)
        self.assertEqual(semantic.scope_digest(config, snapshot_e), digest_a,
                         "a content edit that preserves the path set and chunk count must not re-prompt")
        self.assertTrue(semantic._consent_matches(self.root, config, snapshot_e),
                        "the stored consent still matches after a same-scope content edit")
        fake_e = FakeTransport()
        with mock.patch("builtins.input", side_effect=EOFError):
            kept = semantic.build_index(self.root, transport=fake_e)
        self.assertIn("index built", "\n".join(kept))
        self.assertGreater(len(fake_e.calls), 0, "the stored consent still authorizes an explicit rebuild")
        self.assertEqual(json.loads(consent_path.read_text(encoding="utf-8")), consent_a,
                         "a same-scope content edit never rewrites the stored consent")
        # Case 2: a NEW eligible file → new path set and counts.
        (self.root / "src" / "gamma.py").write_text("def gamma():\n    return 3\n", encoding="utf-8")
        git_in(self.root, "add", "-A")
        git_in(self.root, "commit", "-q", "-m", "add gamma")
        snapshot_g = semantic.inventory(self.root, config)
        self.assertEqual(len(snapshot_g["files"]), len(snapshot_e["files"]) + 1, "one more eligible file")
        digest_g = semantic.scope_digest(config, snapshot_g)
        self.assertNotEqual(digest_g, digest_a, "a new eligible file must start a new consent scope")
        fake_eof = FakeTransport()
        with mock.patch("builtins.input", side_effect=EOFError):
            refused = semantic.build_index(self.root, transport=fake_eof)
        self.assertTrue(any("no consent" in line for line in refused), f"expected no-consent refusal, got: {refused}")
        self.assertEqual(fake_eof.calls, [], "zero outbound on refused rebuild after a new file")
        self.assertEqual(json.loads(consent_path.read_text(encoding="utf-8")), consent_a,
                         "stored consent A is untouched until the new scope is approved")
        fake_explicit = FakeTransport()
        rebuilt = semantic.build_index(self.root, transport=fake_explicit, consent=True)
        self.assertIn("index built", "\n".join(rebuilt))
        self.assertGreater(len(fake_explicit.calls), 0, "explicit re-confirmation re-indexes")
        consent_g = json.loads(consent_path.read_text(encoding="utf-8"))
        self.assertEqual(consent_g["scope_digest"], digest_g, "the approved record is bound to the new scope")
        # Case 3: same path set, HIGHER chunk count → new scope, fresh confirmation.
        paths_g = [item.split(":", 1)[0] for item in snapshot_g["files"]]
        lines = "".join(f"value_{index} = {index}\n" for index in range(210))
        (self.root / "src" / "alpha.py").write_text(lines, encoding="utf-8")
        git_in(self.root, "add", "-A")
        git_in(self.root, "commit", "-q", "-m", "grow alpha")
        snapshot_h = semantic.inventory(self.root, config)
        self.assertGreater(snapshot_h["chunks"], snapshot_g["chunks"], "more chunks in the same files")
        self.assertEqual([item.split(":", 1)[0] for item in snapshot_h["files"]], paths_g,
                         "the eligible path set is unchanged by the growth")
        digest_h = semantic.scope_digest(config, snapshot_h)
        self.assertNotEqual(digest_h, digest_g, "a chunk-count change must start a new consent scope")
        fake_h = FakeTransport()
        with mock.patch("builtins.input", side_effect=EOFError):
            refused_h = semantic.build_index(self.root, transport=fake_h)
        self.assertTrue(any("no consent" in line for line in refused_h), f"expected no-consent refusal, got: {refused_h}")
        self.assertEqual(fake_h.calls, [], "zero outbound on refused rebuild after a chunk-count change")
        self.assertEqual(json.loads(consent_path.read_text(encoding="utf-8")), consent_g,
                         "stored consent G is untouched until the grown scope is approved")
        fake_final = FakeTransport()
        rebuilt_h = semantic.build_index(self.root, transport=fake_final, consent=True)
        self.assertIn("index built", "\n".join(rebuilt_h))
        self.assertGreater(len(fake_final.calls), 0, "explicit re-confirmation re-indexes the grown scope")


class SemanticSingleReadTests(KitRepository):
    """The embedded text and the hash recorded for it come from one read (#130)."""

    def test_file_edited_between_inventory_and_indexing_is_never_recorded_under_a_stale_hash(self) -> None:
        git_in(self.root, "init", "-q", "-b", "main")
        git_in(self.root, "config", "user.email", "test@example.com")
        git_in(self.root, "config", "user.name", "Test")
        (self.root / "src").mkdir(parents=True, exist_ok=True)
        target = self.root / "src" / "alpha.py"
        target.write_text("def alpha():\n    return 1\n", encoding="utf-8")
        (self.root / "src" / "beta.py").write_text("def beta():\n    return 2\n", encoding="utf-8")
        git_in(self.root, "add", "src")
        git_in(self.root, "commit", "-q", "-m", "initial")
        enable(self.root)
        config = semantic._config(self.root)
        snapshot = semantic.inventory(self.root, config)
        target.write_text("def alpha():\n    return 'edited after the inventory'\n", encoding="utf-8")
        fake = FakeTransport()
        index = semantic._index_inventory(self.root, config, snapshot, fake)
        sent = "".join("".join(call) for call in fake.calls)
        self.assertNotIn("src/alpha.py", [entry["path"] for entry in index["files"]],
                         "a file changed since the inventory is skipped as stale, not recorded")
        self.assertNotIn("edited after the inventory", sent, "unconfirmed edited text must not be sent")
        self.assertEqual(index["counts"]["files"], len(index["files"]))
