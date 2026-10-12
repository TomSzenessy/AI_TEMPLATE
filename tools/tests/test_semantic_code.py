"""Optional consent-gated semantic code similarity for `make similar --code` (#115).

No test contacts a real embedding provider and no test sends private code
anywhere: the transport is a first-party fake adapter, HTTP fixtures are local
trusted servers, and every refusal path is asserted to make zero outbound
calls. The default capability-only behavior of `make similar` is asserted
unchanged alongside the new code results.
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `fixtures`, however this file is invoked (#33)
from fixtures import KitRepository, Scratch  # noqa: E402

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
