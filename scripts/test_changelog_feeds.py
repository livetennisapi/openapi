"""Tests for the changelog feeds. Run: python -m unittest scripts/test_changelog_feeds.py

The first group checks the committed docs/changelog.atom and docs/changelog.json: both are what
the build writes today, both pass their format's rules, and every entry of changelog.html is in
both with the same version and date. The second group breaks copies of the feeds and checks that
each rule catches its fault. The real files are never written.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_reference as br  # noqa: E402
import changelog_feeds as cf  # noqa: E402

ATOM = br.DOCS / "changelog.atom"
JSON_FEED = br.DOCS / "changelog.json"
PAGE = br.DOCS / "changelog.html"
A = "{http://www.w3.org/2005/Atom}"


def build() -> tuple[str, str, str]:
    """(changelog.html, atom, json feed) as the build writes them now."""
    spec = br.load_spec()
    entries = br.changelog_entries(br.CHANGELOG.read_text(encoding="utf-8"))
    reference = (br.DOCS / "reference.html").read_text(encoding="utf-8")
    page, _ = br.build_changelog(spec, reference, entries)
    atom, feed = br.build_changelog_feeds(spec, entries)
    return page, atom, feed


class CommittedFeedsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.atom = ATOM.read_text(encoding="utf-8")
        cls.feed = JSON_FEED.read_text(encoding="utf-8")

    def test_the_build_writes_the_committed_files(self) -> None:
        page, atom, feed = build()
        self.assertEqual(page, self.page, "changelog.html is stale: run scripts/build_reference.py")
        self.assertEqual(atom, self.atom, "changelog.atom is stale: run scripts/build_reference.py")
        self.assertEqual(feed, self.feed, "changelog.json is stale: run scripts/build_reference.py")

    def test_a_rebuild_writes_the_same_bytes(self) -> None:
        self.assertEqual(build(), build())

    def test_the_atom_feed_is_valid_rfc_4287(self) -> None:
        self.assertEqual(cf.atom_problems(self.atom, br.CHANGELOG_ATOM_URL), [])

    def test_the_json_feed_is_valid_json_feed_1_1(self) -> None:
        self.assertEqual(cf.json_feed_problems(self.feed, br.CHANGELOG_JSON_URL), [])
        feed = json.loads(self.feed)
        self.assertEqual(feed["version"], "https://jsonfeed.org/version/1.1")
        self.assertEqual(feed["title"], "Live Tennis API changelog")
        self.assertEqual(feed["home_page_url"], br.CHANGELOG_URL)
        self.assertEqual(feed["feed_url"], br.CHANGELOG_JSON_URL)
        for item in feed["items"]:
            for key in ("id", "url", "title", "summary", "content_html", "date_published"):
                self.assertIsInstance(item.get(key), str, f"{item.get('id')}: {key}")
                self.assertTrue(item[key], f"{item.get('id')}: empty {key}")
            ext = item["_livetennisapi"]
            self.assertTrue(ext["version"] and ext["date"])
            self.assertIsInstance(ext["sections"], list)
            self.assertIsInstance(ext["client_libraries"], list)

    def test_every_page_entry_is_in_both_feeds_with_its_version_and_date(self) -> None:
        self.assertEqual(cf.parity_problems(self.page, self.atom, self.feed, br.CHANGELOG_URL), [])
        page = [(v, d) for v, d, _ in cf.page_entries(self.page)]
        root = ET.fromstring(self.atom.encode())
        atom = [(e.findtext(f"{A}id").split("#v", 1)[1], e.findtext(f"{A}published")[:10])
                for e in root.findall(f"{A}entry")]
        items = json.loads(self.feed)["items"]
        feed = [(i["_livetennisapi"]["version"], i["date_published"][:10]) for i in items]
        self.assertEqual(atom, page)
        self.assertEqual(feed, page)

    def test_every_changelog_heading_is_a_page_entry(self) -> None:
        headings = re.findall(r"^## \[([^\]]+)\] - (\d{4}-\d{2}-\d{2})$",
                              br.CHANGELOG.read_text(encoding="utf-8"), re.M)
        self.assertEqual(len(headings), br.CHANGELOG.read_text(encoding="utf-8").count("\n## "))
        self.assertEqual([(v, d) for v, d, _ in cf.page_entries(self.page)], headings)

    def test_ids_are_the_page_anchors(self) -> None:
        anchors = re.findall(r'<article id="(v[^"]+)">', self.page)
        root = ET.fromstring(self.atom.encode())
        ids = [e.findtext(f"{A}id") for e in root.findall(f"{A}entry")]
        self.assertEqual(ids, [f"{br.CHANGELOG_URL}#{a}" for a in anchors])
        self.assertEqual([i["id"] for i in json.loads(self.feed)["items"]], ids)

    def test_the_pages_link_both_feeds(self) -> None:
        want = {("application/atom+xml", br.CHANGELOG_ATOM_URL),
                ("application/feed+json", br.CHANGELOG_JSON_URL)}
        for name in ("changelog.html", "index.html"):
            links = cf.alternate_links((br.DOCS / name).read_text(encoding="utf-8"))
            self.assertEqual({(l["type"], l["href"]) for l in links}, want, name)
            self.assertTrue(all(l.get("title") for l in links), name)
        body = self.page.split("</head>", 1)[1]
        self.assertIn(f'href="{br.CHANGELOG_ATOM_URL}"', body)
        self.assertIn(f'href="{br.CHANGELOG_JSON_URL}"', body)

    def test_llms_txt_lists_both_feeds(self) -> None:
        llms = (br.DOCS / "llms.txt").read_text(encoding="utf-8")
        self.assertIn(br.CHANGELOG_ATOM_URL, llms)
        self.assertIn(br.CHANGELOG_JSON_URL, llms)


class EntryParsingTest(unittest.TestCase):
    def test_sections_items_and_notes_keep_page_order(self) -> None:
        md = ("### Added\n- **One.** More text\n  continued.\n- Two.\n\n"
              "A note.\n\n### Added (again)\n- Three.\n###  Fixed\n- **Four.**\n### Clarified\nOnly a note.")
        sections = cf.entry_sections(md)
        self.assertEqual([(s["name"], len(s["items"]), s["notes"]) for s in sections],
                         [("Added", 2, ["A note."]), ("Added", 1, []), ("Fixed", 1, []),
                          ("Clarified", 0, ["Only a note."])])
        self.assertEqual(sections[0]["items"][0], "**One.** More text continued.")
        self.assertEqual(cf.section_names(sections), ["Added", "Fixed", "Clarified"])

    def test_the_parse_matches_what_the_page_renders(self) -> None:
        md = ("### Added\n- **Wrapped bold\nacross lines.** And `code\nwrapped`.\n- \n"
              "  more\n\nSee <https://example.com/x>.\n###  Fixed\n- Two.")
        sections = cf.entry_sections(md)
        as_read = [{"name": x["name"], "items": [cf.plain(i) for i in x["items"]],
                    "notes": [cf.plain(n) for n in x["notes"]]} for x in sections]
        self.assertEqual(as_read, cf._page_sections(br._md_block(md)))
        self.assertNotIn("**", br._md_block(md))
        self.assertNotIn("&lt;https", br._md_block(md))

    def test_an_item_before_any_heading_has_no_section_name(self) -> None:
        self.assertEqual(cf.entry_sections("- **Loose.** Item."),
                         [{"name": None, "items": ["**Loose.** Item."], "notes": []}])

    def test_title_and_summary(self) -> None:
        sections = cf.entry_sections("### Fixed\n- **A `x` reads right.** `[1]` is 1.\n- **B.** b.")
        self.assertEqual(cf.entry_title("1.0.0", sections), "1.0.0: A x reads right, and 1 more change")
        self.assertEqual(cf.entry_summary(sections), "Fixed: A x reads right. B.")

    def test_the_lead_stops_at_the_first_bold_run(self) -> None:
        self.assertEqual(cf.lead("**`Price.side`** now follows p1. Then **the mapping is verified.** More."),
                         "Price.side now follows p1.")

    def test_client_versions(self) -> None:
        names = cf.names_for_clients(br.CLIENTS, br.CHANGELOG_CLIENT_WORDS)
        text = ("The samples cover Python 1.8.0, JavaScript 1.10.2, Go 1.3.0 and PHP 1.2.0. They also "
                "cover .NET 1.2.1, Dart 1.2.1, Swift 1.1.1 and R 0.2.0. JS 1.10.2 again. It builds with "
                "Swift 5.10 on Python 3.9, with `livetennisapi-export` 0.1.0 and livetennisapi-mcp@1.6.1.")
        got = [(c["client"], c["version"]) for c in cf.client_versions(text, names)]
        self.assertEqual(got, [("Python", "1.8.0"), ("JavaScript", "1.10.2"), ("Go", "1.3.0"),
                               ("PHP", "1.2.0"), (".NET", "1.2.1"), ("Dart", "1.2.1"),
                               ("Swift", "1.1.1"), ("R", "0.2.0"),
                               ("livetennisapi-export", "0.1.0"), ("livetennisapi-mcp", "1.6.1")])

    def test_a_runtime_version_is_not_a_client_version(self) -> None:
        names = cf.names_for_clients(br.CLIENTS, br.CHANGELOG_CLIENT_WORDS)
        text = "Built with Go 1.25.0, R 4.4.1, Python 3.12.4, Swift 5.10.1 and PHP 8.3.12."
        self.assertEqual(cf.client_versions(text, names), [])

    def test_a_heading_the_parser_cannot_read_stops_the_build(self) -> None:
        good = "## [1.0.1] - 2026-01-02\n- a\n\n"
        for bad in ("## [1.0.0] \u2014 2026-01-01", "##[1.0.0] - 2026-01-01",
                    " ## [1.0.0] - 2026-01-01", "### [1.0.0] - 2026-01-01", "## 1.0.0 - 2026-01-01"):
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                br.changelog_entries(good + bad + "\n- b\n")
        self.assertEqual(len(br.changelog_entries(good + "### Added\n- b\n")), 1)


class RulesCatchFaultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.page = PAGE.read_text(encoding="utf-8")
        cls.atom = ATOM.read_text(encoding="utf-8")
        cls.feed = JSON_FEED.read_text(encoding="utf-8")

    def atom_faults(self, old: str, new: str, count: int = 1) -> list[str]:
        self.assertIn(old, self.atom)
        return cf.atom_problems(self.atom.replace(old, new, count), br.CHANGELOG_ATOM_URL)

    def assertCaught(self, problems: list[str], fragment: str) -> None:
        self.assertTrue(any(fragment in p for p in problems), f"{fragment!r} not in {problems}")

    def test_atom_faults(self) -> None:
        first_id = re.search(r"<entry>\n<id>([^<]+)</id>", self.atom)[1]
        second_id = re.findall(r"<entry>\n<id>([^<]+)</id>", self.atom)[1]
        self.assertCaught(self.atom_faults(f"<id>{second_id}</id>", f"<id>{first_id}</id>"),
                          "repeats an earlier entry's")
        self.assertCaught(self.atom_faults("<published>2026", "<published>26"), "RFC 3339")
        self.assertCaught(self.atom_faults("<updated>2026", "<updated>2026-13-01T00:00:00Z<x/>2026"),
                          "RFC 3339")
        self.assertCaught(cf.atom_problems(re.sub(r"<updated>[^<]*</updated>\n", "", self.atom, count=1)),
                          "feed: no atom:updated")
        self.assertCaught(cf.atom_problems(re.sub(r"<author>.*?</author>\n", "", self.atom)),
                          "no atom:author")
        self.assertCaught(self.atom_faults('href="https://docs.livetennisapi.com/changelog.html#',
                                           'href="changelog.html#'), "is not absolute")
        self.assertCaught(self.atom_faults("&lt;/ul&gt;</content>", "</content>"), "never closed")
        self.assertCaught(self.atom_faults('<content type="html">', '<content type="markdown">'),
                          "is neither text, html, xhtml nor a media type")
        self.assertCaught(self.atom_faults("<title type=\"text\">1.", "<title>x</title><title>1."),
                          "at most one allowed")
        self.assertCaught(self.atom_faults('<category term="Added"/>', '<category term=""/>'), "without term")
        self.assertCaught(self.atom_faults("</feed>", "</fee>"), "not well-formed")
        self.assertCaught(cf.atom_problems(self.atom, "https://example.com/other.atom"), "self link")

    def json_faults(self, change) -> list[str]:
        feed = json.loads(self.feed)
        change(feed)
        return cf.json_feed_problems(json.dumps(feed), br.CHANGELOG_JSON_URL)

    def test_json_feed_faults(self) -> None:
        self.assertCaught(self.json_faults(lambda f: f.update(version="https://jsonfeed.org/version/1")),
                          "version is")
        self.assertCaught(self.json_faults(lambda f: f.pop("title")), "title is required")
        self.assertCaught(self.json_faults(lambda f: f["items"][1].update(id=f["items"][0]["id"])),
                          "repeats an earlier item's")
        self.assertCaught(self.json_faults(lambda f: f["items"][0].pop("id")), "non-empty string")
        self.assertCaught(self.json_faults(lambda f: f["items"][0].pop("content_html")),
                          "needs content_html or content_text")
        self.assertCaught(self.json_faults(lambda f: f["items"][0].update(date_published="2026-11-20")),
                          "RFC 3339")
        self.assertCaught(self.json_faults(lambda f: f["items"][0].update(livetennisapi={})), "unknown key")
        self.assertCaught(self.json_faults(lambda f: f.update(feed_url="http://x")), "https URL")
        self.assertCaught(self.json_faults(lambda f: f.update(authors=[{}])), "name, url or avatar")

    def test_more_atom_faults(self) -> None:
        self.assertCaught(self.atom_faults('<content type="html">', '<content type="multipart/mixed">'),
                          "composite type")
        self.assertCaught(self.atom_faults('<content type="html">', '<content type="image/png">')
                          + cf.atom_problems(re.sub(r"<summary[^>]*>.*?</summary>\n", "",
                                                    self.atom.replace('<content type="html">',
                                                                      '<content type="image/png">', 1),
                                                    count=1)), "needs an atom:summary")
        self.assertCaught(self.atom_faults('<title type="text">1.', '<title type="text"><b/>1.'),
                          "holds child elements")
        self.assertCaught(self.atom_faults("</name>", "</name><uri>https://a.example</uri>"),
                          "more than one atom:uri")
        self.assertCaught(self.atom_faults('<category term="Added"/>',
                                           '<category term="Added" scheme="not an iri"/>'), "not an IRI")
        self.assertEqual([p for p in self.atom_faults("<updated>2026-11-20T00:00:00Z",
                                                      "<updated>2016-12-31T23:59:60Z") if "RFC 3339" in p], [])

    def test_parity_faults(self) -> None:
        def broken(old: str, new: str) -> list[str]:
            self.assertIn(old, self.atom)
            return cf.parity_problems(self.page, self.atom.replace(old, new), self.feed, br.CHANGELOG_URL)

        self.assertCaught(broken('<content type="html">', '<content type="text">'), "not type html")
        self.assertCaught(broken('<summary type="text">', '<summary type="text">WRONG '), "disagree on title")
        self.assertCaught(broken('<category term="Added"/>', ""), "categories")
        self.assertCaught(broken('changelog.html#v1.13.88"/>', 'changelog.html#v0.0.0"/>'), "link")
        feed = json.loads(self.feed)
        feed["items"][0]["_livetennisapi"]["sections"][0]["items"].pop()
        self.assertCaught(cf.parity_problems(self.page, self.atom, json.dumps(feed), br.CHANGELOG_URL),
                          "sections, items or notes differ")
        feed = json.loads(self.feed)
        feed["items"][1]["_livetennisapi"]["client_libraries"] = []
        self.assertCaught(cf.parity_problems(self.page, self.atom, json.dumps(feed), br.CHANGELOG_URL),
                          "client library versions")
        feed = json.loads(self.feed)
        feed["items"][2]["url"] = "https://example.com/"
        self.assertCaught(cf.parity_problems(self.page, self.atom, json.dumps(feed), br.CHANGELOG_URL),
                          "json feed item for")
        raw_marks = self.page.replace("<li><strong>", "<li>**", 1).replace("</strong>", "**", 2)
        self.assertCaught(cf.parity_problems(raw_marks, self.atom, self.feed, br.CHANGELOG_URL),
                          "differs from changelog.html")


    def test_parity_faults_in_count_dates_and_content(self) -> None:
        dropped = re.sub(r"<entry>.*?</entry>\n", "", self.atom, count=1, flags=re.S)
        self.assertCaught(cf.parity_problems(self.page, dropped, self.feed, br.CHANGELOG_URL),
                          "atom has")
        feed = json.loads(self.feed)
        feed["items"][3]["_livetennisapi"]["date"] = "2000-01-01"
        self.assertCaught(cf.parity_problems(self.page, self.atom, json.dumps(feed), br.CHANGELOG_URL),
                          "json feed item for")
        edited = self.atom.replace("&lt;li&gt;", "&lt;li&gt;Edited ", 1)
        self.assertCaught(cf.parity_problems(self.page, edited, self.feed, br.CHANGELOG_URL),
                          "atom entry for")


if __name__ == "__main__":
    unittest.main()
