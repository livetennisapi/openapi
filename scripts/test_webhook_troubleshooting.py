"""Tests for the webhook troubleshooting section. Run: python -m unittest scripts/test_webhook_troubleshooting.py

The first group checks the committed push-feed-and-webhooks.html: the section and its anchor
exist, the contents list links it, and every header name, path, field and limit in it matches
the spec. The second group runs both verifier snippets against deliveries signed as the spec
describes. The third breaks copies of the spec and checks that the build refuses each one.
The real files are never written.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_reference as br  # noqa: E402

PAGE = br.DOCS / "push-feed-and-webhooks.html"
LLMS = br.DOCS / "llms.txt"
SECRET = "5f2c8e0a9b7d4c3e1f6a8b0c2d4e6f8091a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1"
BODY = b'{"type":"score","match_id":4711,"sequence":118,"delivery_id":"dlv_0f3a"}'


def sign_v1(body: bytes, t: int, secret: str = SECRET) -> str:
    """The header as the createWebhook description defines it."""
    digest = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={digest}"


def section_of(page: str) -> str:
    start = page.index(f'<h2 id="{br.WEBHOOK_TS_ID}">')
    return page[start:page.index("</main>", start)]


def text_of(fragment: str) -> str:
    return html.unescape(" ".join(re.sub(r"<[^>]+>", " ", fragment).split()))


class CommittedSectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = br.load_spec()
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.section = section_of(cls.page)
        cls.prose = re.sub(r"<pre>.*?</pre>", " ", cls.section, flags=re.S)
        cls.text = text_of(cls.section)
        cls.facts = br.webhook_facts(cls.spec)
        cls.post = " ".join(cls.spec["paths"]["/webhooks"]["post"]["description"].split())

    def test_page_is_what_the_build_writes(self) -> None:
        reference = (br.DOCS / "reference.html").read_text(encoding="utf-8")
        pages = br.build_topic_pages(self.spec, reference)
        self.assertEqual(pages["push-feed-and-webhooks"], self.page)

    def test_section_and_anchor_exist_once(self) -> None:
        self.assertEqual(self.page.count(f'id="{br.WEBHOOK_TS_ID}"'), 1)
        self.assertIn(f'<h2 id="{br.WEBHOOK_TS_ID}">{br.WEBHOOK_TS_TITLE}</h2>', self.page)

    def test_contents_links_the_section(self) -> None:
        nav = re.search(r'<nav aria-labelledby="contents-heading">(.*?)</nav>', self.page, re.S)
        self.assertIsNotNone(nav)
        self.assertIn(f'<a href="#{br.WEBHOOK_TS_ID}">{br.WEBHOOK_TS_TITLE}</a>', nav.group(1))
        self.assertIn('<a href="#endpoints">', nav.group(1))
        # The contents list sits before the endpoints, the section after them.
        self.assertLess(self.page.index("contents-heading"), self.page.index('id="endpoints"'))
        self.assertLess(self.page.index('id="createWsToken"'), self.page.index(f'id="{br.WEBHOOK_TS_ID}"'))

    def test_every_entry_has_an_anchor_its_list_links_and_symptom_cause_fix_order(self) -> None:
        entries = br.webhook_troubleshooting(self.spec)
        ids = [i for i, _, _, _ in entries] + ["ts-verifier"]
        self.assertEqual(len(ids), len(set(ids)))
        for i in ids:
            self.assertEqual(self.page.count(f'id="{i}"'), 1, i)
            self.assertIn(f'<li><a href="#{i}">', self.section, i)
        for i, symptom, _, _ in entries:
            block = self.section[self.section.index(f'<h3 id="{i}">'):]
            block = block[:block.index("<h3", 4)]
            self.assertLess(block.index(html.escape(symptom)), block.index("<strong>Cause.</strong>"))
            self.assertLess(block.index("<strong>Cause.</strong>"), block.index("<strong>Fix.</strong>"))

    def test_every_in_page_link_resolves(self) -> None:
        ids = set(re.findall(r'id="([^"]+)"', self.page))
        for target in re.findall(r'href="#([^"]+)"', self.section):
            self.assertIn(target, ids, target)

    def test_every_header_name_is_in_the_spec(self) -> None:
        headers = set(re.findall(r"X-LTAPI-[A-Za-z0-9-]+", self.text))
        self.assertTrue({"X-LTAPI-Signature-V1", "X-LTAPI-Signature", "X-LTAPI-Timestamp"} <= headers)
        spec_headers = set(re.findall(r"X-LTAPI-[A-Za-z0-9-]+", self.post))
        self.assertLessEqual(headers, spec_headers)

    def test_every_operation_named_is_in_the_spec(self) -> None:
        for method, path in re.findall(r"\b(GET|POST|PUT|PATCH|DELETE) (/[A-Za-z0-9_{}/-]*)", self.text):
            path = path.rstrip("/") or "/"
            self.assertIn(path, self.spec["paths"], path)
            self.assertIn(method.lower(), self.spec["paths"][path], f"{method} {path}")

    def test_every_field_and_code_named_is_in_the_spec(self) -> None:
        spec_text = json.dumps(self.spec)
        tokens = set(re.findall(r"[A-Za-z0-9_]+", spec_text))
        for code in re.findall(r"<code>([a-z][a-z0-9_]*)</code>", self.prose):
            self.assertIn(code, tokens, code)
        self.assertIn("webhook_limit", self.text)

    def test_limits_match_the_spec(self) -> None:
        post = self.post
        n = re.search(r"After (\d+) consecutive failures", post).group(1)
        w = re.search(r"Reject a `t` more than (\d+) minutes", post).group(1)
        s = re.search(r"~(\d+)s timeout", post).group(1)
        k = re.search(r"Up to (\d+) webhooks per key", post).group(1)
        d = re.search(r"unchanged until (\d{4}-\d{2}-\d{2})", post).group(1)
        self.assertIn(f"After {n} consecutive failures the webhook is disabled", self.text)
        self.assertIn(f"more than {w} minutes from your clock", self.text)
        self.assertIn(f"t + {w} minutes on your clock", self.text)
        self.assertIn(f"~{s}s timeout", self.text)
        self.assertIn(f"at most {k} webhooks", self.text)
        self.assertIn(f"until {d}", self.text)
        for snippet in ("node", "python"):
            self.assertIn(f"> {int(w) * 60}", br.webhook_snippets(self.spec)[snippet])

    def test_every_number_in_the_prose_is_accounted_for(self) -> None:
        f = self.facts
        allowed = {f["failures"], f["window"], f["timeout"], f["max_hooks"],
                   f"{f['timeout']}s", f"{f['window']}-minute",
                   "201", "409", "3xx", "1000", "32", "64", "00:00", f["legacy_until"],
                   "V1", "v1", "SHA256", "4711"}
        for number in re.findall(r"\b\d[\w:-]*", text_of(self.prose)):
            self.assertTrue(number in allowed or number.startswith(("0-9", "64")), number)

    def test_llms_txt_lists_the_section_and_its_entries(self) -> None:
        llms = LLMS.read_text(encoding="utf-8")
        url = f"{br.DOCS_URL}/push-feed-and-webhooks.html"
        self.assertIn(f"{url}#{br.WEBHOOK_TS_ID}", llms)
        for i, symptom, _, _ in br.webhook_troubleshooting(self.spec):
            self.assertIn(f"- {symptom}: {url}#{i}", llms)


class SnippetTest(unittest.TestCase):
    """Both verifiers accept a delivery signed as the spec says and refuse each fault."""

    NOW = 1_790_000_000

    @classmethod
    def setUpClass(cls) -> None:
        snippets = br.webhook_snippets(br.load_spec())
        namespace: dict = {}
        exec(compile(snippets["python"], "verify_v1", "exec"), namespace)  # noqa: S102
        cls.verify = staticmethod(namespace["verify_v1"])
        cls.node_source = snippets["node"]

    def cases(self) -> list[tuple[str, bytes, str | None, bool]]:
        good = sign_v1(BODY, self.NOW)
        other = sign_v1(BODY, self.NOW, "another-secret").split(",")[1]
        reparsed = json.dumps(json.loads(BODY)).encode()  # ", " and ": " separators
        return [
            ("signed as the spec says", BODY, good, True),
            ("a second v1 value, one matches", BODY, f"t={self.NOW},{other},{good.split(',')[1]}", True),
            ("upper-case hex", BODY, good.upper().replace("T=", "t=").replace("V1=", "v1="), True),
            ("a body serialised again", reparsed, good, False),
            ("no header: never fall back", BODY, None, False),
            ("t outside the window", BODY, sign_v1(BODY, self.NOW - 301), False),
            ("t just inside the window", BODY, sign_v1(BODY, self.NOW - 300), True),
            ("t in milliseconds", BODY, sign_v1(BODY, self.NOW * 1000), False),
            ("t re-stamped, signature kept", BODY, f"t={self.NOW},{sign_v1(BODY, self.NOW - 900).split(',')[1]}", False),
            ("hex one character short", BODY, good[:-1], False),
            ("hex with a non-hex character", BODY, good[:-1] + "g", False),
            ("hex with a non-ASCII character", BODY, good[:-1] + "é", False),
            ("odd garbage", BODY, "t=,v1=,=,", False),
            ("t not a number", BODY, "t=12a," + good.split(",")[1], False),
            ("t in non-ASCII digits", BODY, "t=١٢," + good.split(",")[1], False),
        ]

    def test_python_verifier(self) -> None:
        for name, body, header, want in self.cases():
            with self.subTest(name):
                self.assertIs(self.verify(body, header, SECRET, now=self.NOW), want)

    def test_node_verifier(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        cases = [(n, b.decode("latin-1"), h, w) for n, b, h, w in self.cases()]
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp) / "verify.mjs"
            module.write_text(self.node_source, encoding="utf-8")
            runner = Path(tmp) / "run.mjs"
            runner.write_text(
                "import { verifyV1 } from './verify.mjs';\n"
                f"const cases = {json.dumps(cases)};\n"
                "const out = cases.map(([name, body, header]) =>"
                f" [name, verifyV1(Buffer.from(body, 'latin1'), header, {json.dumps(SECRET)}, {self.NOW})]);\n"
                "console.log(JSON.stringify(out));\n",
                encoding="utf-8",
            )
            run = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        got = dict(json.loads(run.stdout))
        for name, _, _, want in cases:
            with self.subTest(name):
                self.assertIs(got[name], want)


class DriftTest(unittest.TestCase):
    """A spec that stops saying what the section relies on fails the build."""

    def setUp(self) -> None:
        self.spec = copy.deepcopy(br.load_spec())
        self.post = self.spec["paths"]["/webhooks"]["post"]

    def edit(self, old: str, new: str) -> None:
        self.assertIn(old, self.post["description"])
        self.post["description"] = self.post["description"].replace(old, new)

    def refused(self) -> None:
        with self.assertRaises(SystemExit):
            br.webhook_troubleshooting_html(self.spec)

    def test_untouched_spec_builds(self) -> None:
        self.assertIn("After 25 consecutive failures", br.webhook_troubleshooting_html(self.spec))

    def test_failure_count_changed_in_one_place(self) -> None:
        self.edit("25 consecutive failures", "30 consecutive failures")
        self.refused()

    def test_failure_count_changed_in_both_places_moves_the_page(self) -> None:
        self.edit("25 consecutive failures", "30 consecutive failures")
        enabled = self.spec["components"]["schemas"]["Webhook"]["properties"]["enabled"]
        enabled["description"] = enabled["description"].replace("25", "30")
        out = br.webhook_troubleshooting_html(self.spec)
        self.assertIn("After 30 consecutive failures", out)
        self.assertNotRegex(text_of(out), r"\b25\b")

    def test_window_changed_moves_the_snippets(self) -> None:
        self.edit("more than 5 minutes", "more than 2 minutes")
        self.edit("`t` + 5 minutes", "`t` + 2 minutes")
        snippets = br.webhook_snippets(self.spec)
        self.assertIn("> 120", snippets["node"])
        self.assertIn("> 120", snippets["python"])

    def test_windows_that_disagree(self) -> None:
        self.edit("more than 5 minutes", "more than 2 minutes")
        self.refused()

    def test_header_renamed(self) -> None:
        self.edit("Verify the `X-LTAPI-Signature-V1` header", "Verify the `X-LTAPI-Sig` header")
        self.refused()

    def test_fallback_rule_dropped(self) -> None:
        self.edit("never fall back to the old header", "fall back when you like")
        self.refused()

    def test_timeout_reworded(self) -> None:
        self.edit("~3s timeout", "~5s timeout")
        self.assertIn("~5s timeout", br.webhook_troubleshooting_html(self.spec))

    def test_redirects_followed(self) -> None:
        self.edit("redirects disabled", "redirects followed")
        self.refused()

    def test_events_default_changed(self) -> None:
        body = self.post["requestBody"]["content"]["application/json"]["schema"]["properties"]
        body["events"]["default"] = ["score", "point"]
        self.refused()

    def test_update_operation_added(self) -> None:
        self.spec["paths"]["/webhooks/{webhookId}"]["patch"] = {"responses": {}}
        self.refused()

    def test_schema_field_removed(self) -> None:
        del self.spec["components"]["schemas"]["Webhook"]["properties"]["consecutive_failures"]
        self.refused()


if __name__ == "__main__":
    unittest.main()
