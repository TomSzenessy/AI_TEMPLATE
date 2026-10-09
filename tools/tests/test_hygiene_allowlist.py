"""#61: file-hygiene exempts declared paths visibly, and ignores code that only names a credential."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import Scratch  # noqa: E402

from kit import core  # noqa: E402
from kit.checkrun import run_checks  # noqa: E402
from kit.registry import Registry  # noqa: E402
from kit.core import RepoctlError  # noqa: E402

MANIFEST = 'schema = 1\nname = "Demo"\nkind = "template"\nphase = "bootstrap"\nlicense = "UNSELECTED"\nowners = []\n'
ONLY = frozenset({"file-hygiene", "file-hygiene-allowed"})

# Built at runtime so this file is itself clean under the scan it tests.
LITERAL_KEY = "api" + "_key" + " = " + '"' + "k3y" + "9Zx81Qw7Er5Ty2Ui" + '"'
LITERAL_ENV = "STRIPE_SECRET" + "_KEY=" + "abcd1234" + "efgh5678ijkl"
LITERAL_JSON_HEADER = 'headers = {"Authorization": "Bearer ' + "abcd1234efgh5678ijkl" + '"}'
LITERAL_JSON = '{"pass' + 'word": "' + "hunter2hunter2hunter2" + '"}'
LITERAL_EXPORT = "export API_" + "TOKEN=" + "abcd1234efgh5678ijkl"
LITERAL_HEADER = "Authorization" + ": Bearer " + "abcd1234efgh5678ijkl"

AUTH_HELPER = """\
import os
import requests

def headers(token: str) -> dict:
    return {"Authorization": "Bearer " + token}

def fetch(url, session):
    token = os.environ["SERVICE_TOKEN"]
    api_key = os.getenv("SERVICE_API_KEY")
    req = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    auth = "Authorization: Bearer ${token}"
    password = read_password(session.password_file)
    access_token: str = session.access_token
    secret = settings.client_secret
    return req, api_key, auth, password, access_token, secret
"""

ENV_NAME_MAP = 'env_headers = { CONTEXT7_API_KEY = "CONTEXT7_API_KEY" }\n'

AUTH_HELPER_TS = """\
const token = await getToken();
const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
const apiKey = process.env.STRIPE_API_KEY;
export const clientSecret = config.clientSecret;
"""


class CodeScanTests(unittest.TestCase):
    def test_code_that_only_names_a_credential_is_clean(self) -> None:
        for name, text in (("python", AUTH_HELPER), ("typescript", AUTH_HELPER_TS), ("env var name", ENV_NAME_MAP)):
            with self.subTest(name):
                self.assertEqual(core.code_secret_matches(text), [])

    def test_literal_secrets_are_still_flagged(self) -> None:
        for text in (LITERAL_KEY, LITERAL_ENV, LITERAL_HEADER, LITERAL_JSON_HEADER, LITERAL_JSON, LITERAL_EXPORT):
            with self.subTest(text):
                self.assertTrue(core.code_secret_matches(text), text)

    def test_private_key_block_and_token_formats_are_still_flagged(self) -> None:
        block = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIE\n-----END " + "RSA PRIVATE KEY-----"
        self.assertIn("private key", core.code_secret_matches(block))
        self.assertIn("GitHub token", core.code_secret_matches("gh" + "p_" + "A1b2C3d4E5" * 4))

    def test_prose_scan_for_issues_is_unchanged(self) -> None:
        self.assertIn("credential assignment", core.secret_matches("api_key" + " = " + "x" * 12))


class AllowlistTests(Scratch):
    def setUp(self) -> None:
        super().setUp()
        self.write("project.toml", MANIFEST)

    def allow(self, entries: str) -> None:
        self.write("project.toml", MANIFEST + "\n[checks.file-hygiene]\nallow_paths = [" + entries + "]\n")

    def findings(self) -> tuple[list[str], list[str]]:
        return run_checks(self.root, blocking_only=False, only=ONLY)

    def test_auth_helper_passes_without_any_exemption(self) -> None:
        self.write("src/auth.py", AUTH_HELPER)
        self.write("src/auth.ts", AUTH_HELPER_TS)
        self.assertEqual(self.findings(), ([], []))

    def test_literal_secret_and_env_file_fail_without_exemption(self) -> None:
        self.write("src/config.py", LITERAL_KEY + "\n")
        self.write("site/.env.production", "PUBLIC_KEY=pk_live_abcdefghijkl1234\n")
        hard, _ = self.findings()
        self.assertTrue(any("src/config.py" in item for item in hard), hard)
        self.assertTrue(any("site/.env.production" in item for item in hard), hard)

    def test_allowed_path_is_exempt_but_stays_visible_with_its_reason(self) -> None:
        self.write("site/.env.production", "PUBLIC_KEY=pk_live_abcdefghijkl1234\n")
        self.write("test/fixtures/key.pem", "-----BEGIN " + "PRIVATE KEY-----\nAAAA\n-----END " + "PRIVATE KEY-----\n")
        self.allow('{ glob = "site/.env.production", reason = "publishable key, documented as public" }, '
                   '{ glob = "test/fixtures/**", reason = "throwaway test key" }')
        hard, advisory = self.findings()
        self.assertEqual(hard, [])
        text = "\n".join(advisory)
        self.assertIn("site/.env.production", text)
        self.assertIn("publishable key, documented as public", text)
        self.assertIn("test/fixtures/key.pem", text)
        self.assertIn("throwaway test key", text)

    def test_exemption_covers_only_the_matching_path(self) -> None:
        self.write("site/.env.production", "PUBLIC_KEY=pk_live_abcdefghijkl1234\n")
        self.write("src/config.py", LITERAL_KEY + "\n")
        self.allow('{ glob = "site/.env.production", reason = "publishable key, documented as public" }')
        hard, _ = self.findings()
        self.assertEqual(len(hard), 1, hard)
        self.assertIn("src/config.py", hard[0])

    def test_unused_exemption_is_reported_so_it_can_be_deleted(self) -> None:
        self.allow('{ glob = "gone/**", reason = "once held a fixture key" }')
        _, advisory = self.findings()
        self.assertTrue(any("gone/**" in item and "matches no file" in item for item in advisory), advisory)

    def test_symlink_escape_is_not_exemptable(self) -> None:
        self.write("real.txt", "x")
        (self.root / "link.txt").symlink_to("/etc/hosts")
        self.allow('{ glob = "link.txt", reason = "trying to exempt an escape" }')
        hard, _ = self.findings()
        self.assertTrue(any("symlink" in item for item in hard), hard)

    def rejected(self, entries: str) -> str:
        self.allow(entries)
        with self.assertRaises(RepoctlError) as caught:
            Registry(self.root).check_overrides  # noqa: B018 - the property raises
        return str(caught.exception)

    def test_an_entry_without_a_reason_is_a_config_error(self) -> None:
        self.assertIn("reason", self.rejected('{ glob = "a/**" }'))
        self.assertIn("reason", self.rejected('{ glob = "a/**", reason = "short" }'))
        self.assertIn("reason", self.rejected('{ glob = "a/**", reason = "" }'))

    def test_malformed_entries_are_config_errors(self) -> None:
        self.assertIn("glob", self.rejected('{ reason = "a long enough reason" }'))
        self.assertIn("glob", self.rejected('"just/a/string"'))
        self.assertIn("only glob and reason", self.rejected('{ glob = "a/**", reason = "a long enough reason", extra = 1 }'))
        self.assertIn("everything", self.rejected('{ glob = "**", reason = "a long enough reason" }'))

    def test_a_config_error_stops_make_check(self) -> None:
        self.allow('{ glob = "a/**" }')
        self.assertNotEqual(self.cli("check").returncode, 0)

    def test_allow_paths_alone_does_not_downgrade_the_check(self) -> None:
        self.allow('{ glob = "a/**", reason = "a long enough reason" }')
        self.assertEqual(Registry(self.root).check_overrides, {})
        self.write("src/config.py", LITERAL_KEY + "\n")
        hard, _ = self.findings()
        self.assertTrue(hard)

    def test_allow_paths_is_accepted_only_on_file_hygiene(self) -> None:
        self.write("project.toml", MANIFEST + '\n[checks.dead-bindings]\nseverity = "advisory"\nreason = "a long enough reason"\n'
                   'allow_paths = [{ glob = "a", reason = "a long enough reason" }]\n')
        with self.assertRaises(RepoctlError):
            Registry(self.root).check_overrides  # noqa: B018


if __name__ == "__main__":
    unittest.main()
