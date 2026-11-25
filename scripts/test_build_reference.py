"""Tests for the client libraries version compatibility matrix.

Run: python -m unittest scripts/test_build_reference.py

The first group checks the committed client-libraries.html: the compatibility section and its
anchor exist, the contents list links it, and every library row names its current release, the
public API version it targets and its minimum runtime. The release line is each library's own
version, and the API version is the one the spec serves, so the second group breaks copies of
those inputs and checks that the build refuses each one. The real files are never written.
"""

from __future__ import annotations

import copy
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_reference as br  # noqa: E402

PAGE = br.DOCS / "client-libraries.html"


def a_different_version(version: str) -> str:
    """A public API version that is not the current one, for the drift tests.

    Derived from the current version so these tests still exercise a real mismatch after a future
    migration (v1 to v2 and so on), rather than hard-coding the next version.
    """
    match = re.fullmatch(r"v(\d+)", version)
    return f"v{int(match.group(1)) + 1}" if match else version + "x"


def compat_table(html: str) -> str:
    """The rendered compatibility table block."""
    match = re.search(r'aria-label="Version compatibility".*?</table>', html, re.S)
    assert match, "the compatibility table is not on the page"
    return match.group(0)


def compat_rows(html: str) -> list[list[str]]:
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", compat_table(html), re.S)[1:]:
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
        rows.append(cells)
    return rows


class CommittedPageTest(unittest.TestCase):
    """Assertions against the generated file as it is committed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = PAGE.read_text(encoding="utf-8")
        cls.spec = br.load_spec()

    def test_section_and_anchor_present(self) -> None:
        self.assertIn('id="compatibility"', self.html)
        self.assertIn("Which API version and runtime does each library target?", self.html)
        self.assertEqual(self.html.count('id="compatibility"'), 1)

    def test_contents_links_the_section(self) -> None:
        nav = re.search(r'aria-labelledby="contents-heading".*?</nav>', self.html, re.S)
        self.assertIsNotNone(nav, "no contents nav on the page")
        self.assertIn('<a href="#compatibility">', nav.group(0))

    def test_every_in_page_link_in_contents_resolves(self) -> None:
        nav = re.search(r'aria-labelledby="contents-heading".*?</nav>', self.html, re.S).group(0)
        for anchor in re.findall(r'href="#([^"]+)"', nav):
            self.assertIn(f'id="{anchor}"', self.html, f"contents links #{anchor}, which has no target")

    def test_every_library_has_a_row_with_release_api_and_runtime(self) -> None:
        rows = compat_rows(self.html)
        self.assertEqual(len(rows), len(br.CLIENTS))
        by_name = {r[0]: r for r in rows}
        spec_api = br._spec_api_version(self.spec)
        for client in br.CLIENTS:
            with self.subTest(client=client["key"]):
                row = by_name[client["name"]]
                # Library, current release, public API version, minimum runtime.
                self.assertEqual(row[1], client["version"])
                want = br.CLIENT_API_VERSION[client["key"]]
                shown = "Not stated" if want == "not stated" else want
                self.assertEqual(row[2], shown)
                if want != "not stated":
                    self.assertEqual(row[2], spec_api)
                self.assertEqual(row[3], client["runtime"])

    def test_release_line_matches_the_sdk_version(self) -> None:
        # The matrix must not name a release line that differs from the library's own version, the
        # same version the install table and code-samples pin. This is the stated-version guard.
        versions = {r[0]: r[1] for r in compat_rows(self.html)}
        for client in br.CLIENTS:
            self.assertEqual(versions[client["name"]], client["version"])

    def test_spec_api_version_reads_from_the_server(self) -> None:
        self.assertEqual(br._spec_api_version(self.spec), "v1")

    def test_spec_api_version_requires_a_server(self) -> None:
        with self.assertRaises(SystemExit):
            br._spec_api_version({"servers": []})

    def test_spec_api_version_rejects_disagreeing_servers(self) -> None:
        with self.assertRaises(SystemExit):
            br._spec_api_version({"servers": [
                {"url": "https://sandbox.livetennisapi.com/api/public/v1"},
                {"url": "https://api.livetennisapi.com/api/public/v2"},
            ]})

    def test_committed_body_matches_the_generator(self) -> None:
        # The whole generated body, prose and tables and contents, must appear verbatim in the
        # committed page. A hand-edit to any of it, not only a matrix cell, is then caught here as
        # well as by `build_reference.py --check`.
        self.assertIn(br._clients_body(self.spec), self.html)

    def test_release_line_matches_the_code_sample_versions(self) -> None:
        # The release line is pinned to an independent statement of each client's version, so this
        # is not circular: code-samples/sdk-methods.yaml is read from a separate file. This is the
        # build-time guard for "the matrix matches an SDK's stated version" for the language clients.
        methods = br.build_code_samples.load_methods()
        cells = {r[0]: r[1] for r in compat_rows(self.html)}
        by_key = {c["key"]: c for c in br.CLIENTS}
        for key in br.CLIENT_LANGUAGES:
            with self.subTest(client=key):
                stated = str(methods["clients"][key]["version"])
                self.assertEqual(cells[by_key[key]["name"]], stated)

    def test_baseline_does_not_raise(self) -> None:
        br._clients_drift(self.spec)


class DriftTest(unittest.TestCase):
    """Breaking an input must fail the build."""

    def setUp(self) -> None:
        self.spec = br.load_spec()
        self._saved = dict(br.CLIENT_API_VERSION)

    def tearDown(self) -> None:
        br.CLIENT_API_VERSION.clear()
        br.CLIENT_API_VERSION.update(self._saved)

    def test_fails_when_a_row_targets_another_api_version(self) -> None:
        other = a_different_version(br._spec_api_version(self.spec))
        br.CLIENT_API_VERSION["python"] = other
        with self.assertRaises(SystemExit) as caught:
            br._clients_drift(self.spec)
        self.assertIn(f"targets API {other}", str(caught.exception))

    def test_fails_when_the_spec_moves_to_a_new_version(self) -> None:
        other = a_different_version(br._spec_api_version(self.spec))
        spec = copy.deepcopy(self.spec)
        spec["servers"][0]["url"] = f"https://api.livetennisapi.com/api/public/{other}"
        with self.assertRaises(SystemExit) as caught:
            br._clients_drift(spec)
        self.assertIn(f"spec serves {other}", str(caught.exception))

    def test_fails_when_a_row_has_no_api_version(self) -> None:
        br.CLIENT_API_VERSION.pop("swift")
        with self.assertRaises(SystemExit) as caught:
            br._clients_drift(self.spec)
        self.assertIn("swift", str(caught.exception))
        self.assertIn("no public API version", str(caught.exception))

    def test_fails_when_api_version_names_an_unknown_row(self) -> None:
        # Give the orphan the current version so a version mismatch cannot mask the orphan check:
        # only the orphan check can make this fail, whatever the current API version is.
        br.CLIENT_API_VERSION["ghost"] = br._spec_api_version(self.spec)
        with self.assertRaises(SystemExit) as caught:
            br._clients_drift(self.spec)
        self.assertIn("ghost", str(caught.exception))

    def test_body_builder_runs_the_drift_check(self) -> None:
        # The guard is only useful if the page builder actually calls it. Break a row and confirm
        # that building the body (not just calling _clients_drift directly) fails.
        br.CLIENT_API_VERSION["python"] = a_different_version(br._spec_api_version(self.spec))
        with self.assertRaises(SystemExit):
            br._clients_body(self.spec)

    def test_not_stated_is_rendered_and_skipped(self) -> None:
        # A library with no stated base URL shows "Not stated" and is not compared with the spec
        # version. None do today, so this exercises that otherwise dead branch.
        br.CLIENT_API_VERSION["r"] = "not stated"
        br._clients_drift(self.spec)  # must not raise: "not stated" is skipped
        r_row = next(row for row in compat_rows(br._clients_body(self.spec))
                     if row[0] == "R client")
        self.assertEqual(r_row[2], "Not stated")


if __name__ == "__main__":
    unittest.main()
