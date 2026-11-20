"""The changelog as an Atom feed and a JSON Feed, and the checks that keep them honest.

build_reference.py parses CHANGELOG.md once and hands the same entries to the changelog page
and to the two feeds here, so a feed cannot say anything the page does not. Each entry's
content is the very HTML its <article> on changelog.html carries, and the build compares the
three outputs entry by entry (parity_problems).

Nothing in either feed depends on when the build ran. An entry's id is its anchor on the page,
its dates are the date in its heading, and the feed's own date is the newest entry's. A rebuild
writes the same bytes, so `build_reference.py --check` covers both files, and a feed reader never
sees an old entry as new. The flip side: rewording an old entry changes its content but not its
date, so a reader may not show the edit. The changelog only states days, so entries released on
the same day share a timestamp, as entries of the corrections feed do.

- docs/changelog.atom is Atom 1.0 (RFC 4287). Its shape follows the corrections log feed at
  livetennisapi.com/data/corrections.atom: page anchors as ids, dates at 00:00Z, a self and an
  alternate link, the author, the icon, the rights, a plain-text summary on every entry.
- docs/changelog.json is JSON Feed 1.1. The parsed fields (version, date, the sections with
  their items and notes, the client library versions an entry names) sit in each item's
  `_livetennisapi` object. JSON Feed lets a publisher add objects whose names start with an
  underscore. The object's `about` link is llms.txt, which describes it.

atom_problems() and json_feed_problems() check the rules of the two formats with the standard
library, so the CI job needs nothing beyond PyYAML. scripts/test_changelog_feeds.py breaks
copies of both feeds and checks that each rule catches its fault.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Iterable
from xml.etree import ElementTree as ET

ATOM_NS = "http://www.w3.org/2005/Atom"
JSON_FEED_VERSION = "https://jsonfeed.org/version/1.1"
EXT_KEY = "_livetennisapi"


# --------------------------------------------------------------------------- entry structure --

def entry_sections(body_md: str) -> list[dict[str, Any]]:
    """[{name, items, notes}] from one entry's Markdown, in page order, read line by line by the
    same rules as _md_block, so the feeds hold exactly the items and paragraphs the page shows.

    A line starting `### ` opens a section, named by the first word after it, so "Added (spec
    catch-up ...)" is Added. A line starting `- ` opens an item. A non-blank line after an item
    continues it, indented or not, and a blank line closes it. Any other line is a paragraph,
    kept as a note of the section it sits in. A section that appears twice (1.1.0 has two Added,
    with a note between them) stays two sections, so the note keeps its place. Content before any
    heading (1.13.44 has an item there) goes in a section whose name is None. Items and notes keep
    their Markdown."""
    sections: list[dict[str, Any]] = []
    item: list[str] | None = None
    para: list[str] = []

    def current() -> dict[str, Any]:
        if not sections:
            sections.append({"name": None, "items": [], "notes": []})
        return sections[-1]

    def close() -> None:
        nonlocal item
        if item is not None:
            current()["items"].append(" ".join(item))
            item = None
        if para:
            current()["notes"].append(" ".join(para))
            para.clear()

    for raw in body_md.splitlines():
        line = raw.rstrip()
        if line.startswith("### "):
            close()
            words = line[4:].split()
            sections.append({"name": words[0].rstrip(":") if words else None, "items": [], "notes": []})
        elif line.startswith("- "):
            close()
            item = [line[2:]]
        elif not line:
            close()
        elif item is not None:
            item.append(line.strip())
        else:
            para.append(line.strip())
    close()
    return sections


_CODE_SPAN = re.compile(r"`[^`]+`")
_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")


def autolinks(md: str) -> list[re.Match[str]]:
    """The Markdown autolinks (<https://...>) in a line, leaving out any inside a code span,
    which is literal text. _md_block links these and plain() drops their brackets, by one rule."""
    spans = [m.span() for m in _CODE_SPAN.finditer(md)]
    return [m for m in _AUTOLINK.finditer(md)
            if not any(a <= m.start() < b for a, b in spans)]


_PLAIN_SUBS = [
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"`([^`]+)`"), r"\1"),
]


def plain(md: str) -> str:
    """The text a reader sees, without the Markdown marks the changelog uses."""
    for m in reversed(autolinks(md)):
        md = md[:m.start()] + m[1] + md[m.end():]
    for rx, sub in _PLAIN_SUBS:
        md = rx.sub(sub, md)
    return " ".join(md.split())


# A sentence ends at . ! or ? followed by a space and a capital, a digit, a quote or a bracket.
# Dots inside a version number or a path are never followed by a space, so they do not end one.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
# The opening bold run, up to its first closing **, when it ends in a full stop or the like.
_BOLD_LEAD = re.compile(r"^\*\*((?:(?!\*\*).)+?[.!?])\*\*")


def lead(md: str) -> str:
    """What an item says it changed. Most items open with that in bold, a sentence or two ending
    in a full stop, and then it is the whole bold text. A bold run without one (a field name such
    as **`Price.side`**) is part of a longer sentence, so then it is the first sentence."""
    m = _BOLD_LEAD.match(md.strip())
    if m:
        return plain(m[1])
    return _SENTENCE_END.split(plain(md), 1)[0]


def _items(sections: list[dict[str, Any]]) -> list[str]:
    return [i for s in sections for i in s["items"]]


def _notes(sections: list[dict[str, Any]]) -> list[str]:
    return [n for s in sections for n in s["notes"]]


SUMMARY_ITEMS = 2


def entry_summary(sections: list[dict[str, Any]]) -> str:
    """What the first two items say they changed, each after its section's name, and how many
    more there are. JSON Feed describes a summary as a sentence or two, and the full entry is in
    the content. An entry with no items (none today) gets the first sentence of its first note."""
    parts: list[str] = []
    shown = total = 0
    for s in sections:
        total += len(s["items"])
        leads = [lead(i) for i in s["items"][:SUMMARY_ITEMS - shown]]
        if leads:
            shown += len(leads)
            parts.append(f"{s['name']}: {' '.join(leads)}" if s["name"] else " ".join(leads))
    if total > shown:
        more = total - shown
        parts.append(f"Plus {more} more change{'s' if more > 1 else ''}.")
    if not parts and _notes(sections):
        parts.append(lead(_notes(sections)[0]))
    return " ".join(parts)


TITLE_MAX = 160


def entry_title(version: str, sections: list[dict[str, Any]]) -> str:
    """"1.13.79: The super-tiebreak example in Score.games reads right, and 1 more change"."""
    items = _items(sections)
    notes = _notes(sections)
    first = lead(items[0]) if items else (lead(notes[0]) if notes else "")
    if not first:
        return version
    first = first.rstrip(".")
    if len(first) > TITLE_MAX:
        first = first[:TITLE_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    more = len(items) - 1
    tail = f", and {more} more change{'s' if more > 1 else ''}" if more > 0 else ""
    return f"{version}: {first}{tail}"


def section_names(sections: list[dict[str, Any]]) -> list[str]:
    """The named sections of an entry, once each, in order: the Atom categories and JSON tags."""
    return list(dict.fromkeys(s["name"] for s in sections if s["name"]))


def _version_key(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


# A bare version right after one of these words is the spec's or the changelog's, never a client's.
_NOT_A_CLIENT = {"spec", "api", "openapi", "changelog", "entry", "info.version"}


def client_versions(texts: str | Iterable[str], names: dict[str, tuple[str, str, str]]) -> list[dict[str, str]]:
    """The client library versions a text names, in order, once each.

    `names` maps each way the changelog writes a client ("Python", "JS", "livetennisapi-ai") to
    (client name, package, newest published version). A three-part version right after a name
    counts ("Python 1.8.0", "livetennisapi-mcp@1.6.5", "the Python client to 1.8.0"). So does a bare version later in the same
    item, of the same major version as the client just named ("JavaScript 1.10.3 fixes what
    failed in 1.10.2"). A version above the newest published one is a runtime or a toolchain,
    not the client: "Python 3.12.4" or "Swift 5.10.1" is not read as a client version. The newest
    versions come from CLIENTS, which check_client_versions.py keeps in step with the registries.
    Pass the items one by one, so a name never reaches into the next item."""
    if not names:
        return []
    if isinstance(texts, str):
        texts = [texts]
    alternation = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    rx = re.compile(rf"(?<![\w.-])(?:({alternation})(?:\s+(?:client|library|package))?"
                    rf"(?:\s+(?:to|at|from|in))?(?:\s+v?|@)|(?:(\S+)\s+)?v?)"
                    rf"(\d+\.\d+\.\d+)(?![\w-]|\.\d)")
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for text in texts:
        last: tuple[str, str, str, int] | None = None
        for m in rx.finditer(plain(text)):
            version = m[3]
            if m[1]:
                client, package, newest = names[m[1]]
                if _version_key(version) > _version_key(newest):
                    continue
                last = (client, package, newest, _version_key(version)[0])
            elif last is None or (m[2] or "").lower() in _NOT_A_CLIENT:
                continue
            else:
                client, package, newest, major = last
                if _version_key(version) > _version_key(newest) or _version_key(version)[0] != major:
                    continue
            if (client, version) not in seen:
                seen.add((client, version))
                out.append({"client": client, "package": package, "version": version})
    return out


def feed_entries(entries: list[dict[str, Any]], render: Any, page_url: str,
                 client_names: dict[str, tuple[str, str, str]]) -> list[dict[str, Any]]:
    """The feed view of changelog_entries(): everything both feeds need, computed once."""
    out = []
    for e in entries:
        sections = entry_sections(e["body_md"])
        out.append({
            "version": e["version"],
            "date": e["date"],
            "id": f"{page_url}#v{e['version']}",
            "url": f"{page_url}#v{e['version']}",
            "title": entry_title(e["version"], sections),
            "summary": entry_summary(sections),
            "content_html": render(e["body_md"]),
            "sections": sections,
            "tags": section_names(sections),
            "clients": client_versions([*_items(sections), *_notes(sections)], client_names),
        })
    return out


# ------------------------------------------------------------------------------------ writers --

def _x(text: str) -> str:
    """XML text and attribute escaping: &, <, > and the double quote."""
    return html.escape(text, quote=False).replace('"', "&quot;")


def _stamp(date: str) -> str:
    """A changelog date as an RFC 3339 instant. The changelog states the day only, so 00:00Z."""
    return f"{date}T00:00:00Z"


def build_atom(items: list[dict[str, Any]], meta: dict[str, str]) -> str:
    """Atom 1.0. One element per line, so a new version shows in a diff as a block of new lines."""
    # The newest date in the feed, not the first entry's: the same thing while the changelog stays
    # newest first, and still right if it ever does not.
    updated = _stamp(max(it["date"] for it in items)) if items else _stamp(meta["fallback_date"])
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<feed xmlns="{ATOM_NS}" xml:lang="en">',
        f'<id>{_x(meta["page_url"])}</id>',
        f'<title type="text">{_x(meta["title"])}</title>',
        f'<subtitle type="text">{_x(meta["description"])}</subtitle>',
        f'<updated>{updated}</updated>',
        f'<link rel="self" type="application/atom+xml" href="{_x(meta["atom_url"])}"/>',
        f'<link rel="alternate" type="text/html" href="{_x(meta["page_url"])}"/>',
        f'<link rel="alternate" type="application/feed+json" href="{_x(meta["json_url"])}"/>',
        f'<author><name>{_x(meta["author"])}</name><uri>{_x(meta["author_url"])}</uri></author>',
        f'<icon>{_x(meta["icon"])}</icon>',
        f'<rights type="text">{_x(meta["rights"])}</rights>',
    ]
    for it in items:
        stamp = _stamp(it["date"])
        cats = [f'<category term="{_x(name)}"/>' for name in it["tags"]]
        cats += [
            f'<category term="{_x(c["client"])} {_x(c["version"])}" scheme="{_x(meta["clients_url"])}"/>'
            for c in it["clients"]
        ]
        lines += [
            "<entry>",
            f'<id>{_x(it["id"])}</id>',
            f'<title type="text">{_x(it["title"])}</title>',
            f"<published>{stamp}</published>",
            f"<updated>{stamp}</updated>",
            f'<link rel="alternate" type="text/html" href="{_x(it["url"])}"/>',
            *cats,
            f'<summary type="text">{_x(it["summary"])}</summary>',
            f'<content type="html">{_x(it["content_html"])}</content>',
            "</entry>",
        ]
    lines.append("</feed>")
    return "\n".join(lines) + "\n"


def build_json_feed(items: list[dict[str, Any]], meta: dict[str, str]) -> str:
    """JSON Feed 1.1, with the parsed fields of each entry under `_livetennisapi`."""
    feed = {
        "version": JSON_FEED_VERSION,
        "title": meta["title"],
        "home_page_url": meta["page_url"],
        "feed_url": meta["json_url"],
        "description": meta["description"],
        "icon": meta["icon"],
        "favicon": meta["icon"],
        "language": "en",
        "authors": [{"name": meta["author"], "url": meta["author_url"]}],
        "items": [
            {
                "id": it["id"],
                "url": it["url"],
                "title": it["title"],
                "summary": it["summary"],
                "content_html": it["content_html"],
                "date_published": _stamp(it["date"]),
                "tags": it["tags"],
                EXT_KEY: {
                    "about": meta["ext_about"],
                    "version": it["version"],
                    "date": it["date"],
                    "sections": [
                        {"name": s["name"], "items": [plain(i) for i in s["items"]],
                         "notes": [plain(n) for n in s["notes"]]}
                        for s in it["sections"]
                    ],
                    "client_libraries": it["clients"],
                },
            }
            for it in items
        ],
    }
    return json.dumps(feed, ensure_ascii=False, indent=1) + "\n"


# ----------------------------------------------------------------------------------- checks --

_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$")
# A scheme, a colon, no whitespace, and every % starting a two-digit hex escape (RFC 3987 2.2).
_ABSOLUTE_IRI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:(?:[^\s%]|%[0-9A-Fa-f]{2})+$")
_TEXT_TYPES = {"text", "html", "xhtml"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
         "track", "wbr"}


def _is_rfc3339(value: str | None) -> bool:
    if not value or not _RFC3339.match(value):
        return False
    try:
        # RFC 3339 allows a leap second (23:59:60), which datetime cannot hold.
        datetime.fromisoformat(value.replace("Z", "+00:00").replace(":60", ":59", 1))
    except ValueError:
        return False
    return True


class _Balance(HTMLParser):
    """Collects tag nesting faults in an HTML fragment: a feed reader shows escaped HTML as is."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.faults: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1] != tag:
            self.faults.append(f"</{tag}> closes {self.stack[-1] if self.stack else 'nothing'}")
        else:
            self.stack.pop()


def html_fragment_problems(fragment: str) -> list[str]:
    p = _Balance()
    p.feed(fragment)
    p.close()
    return p.faults + [f"<{t}> never closed" for t in p.stack]


def _a(tag: str) -> str:
    return f"{{{ATOM_NS}}}{tag}"


def _check_text_construct(el: ET.Element, where: str, out: list[str]) -> None:
    """RFC 4287 3.1: type is text, html or xhtml. Text and html hold no child elements (3.1.1.1,
    3.1.1.2), and html must be markup a reader can show. Xhtml is one xhtml:div (3.1.1.3)."""
    kind = el.get("type", "text")
    if kind not in _TEXT_TYPES:
        out.append(f"{where}: type {kind!r} is not text, html or xhtml")
    elif kind in ("text", "html") and len(el):
        out.append(f"{where}: a {kind} construct holds child elements")
    elif kind == "html":
        out += [f"{where}: {f}" for f in html_fragment_problems(el.text or "")]
    elif kind == "xhtml":
        kids = list(el)
        if len(kids) != 1 or kids[0].tag != "{http://www.w3.org/1999/xhtml}div":
            out.append(f"{where}: xhtml content must be one xhtml:div")


def _check_content(el: ET.Element, entry: ET.Element, where: str, out: list[str]) -> None:
    """RFC 4287 4.1.3: content is a Text construct when its type is text, html or xhtml, or
    names a MIME media type. A composite type is not allowed. Content with a src, or content
    that is neither text nor XML (so Base64), needs an atom:summary on the entry (4.1.1.1)."""
    kind = el.get("type", "text")
    src = el.get("src")
    if src is not None:
        # 4.1.3.2: content with a src is empty, and a type it gives is a media type.
        if (el.text or "").strip() or len(el):
            out.append(f"{where}: content with a src must be empty")
        if el.get("type") is not None and "/" not in kind:
            out.append(f"{where}: content with a src needs a media type, not {kind!r}")
        if not _ABSOLUTE_IRI.match(src):
            out.append(f"{where}: src {src!r} is not an absolute IRI")
    elif kind in _TEXT_TYPES:
        _check_text_construct(el, where, out)
        return
    if kind not in _TEXT_TYPES and "/" not in kind:
        out.append(f"{where}: type {kind!r} is neither text, html, xhtml nor a media type")
        return
    if kind.lower().startswith(("multipart/", "message/")):
        out.append(f"{where}: composite type {kind!r} is not allowed")
    textual = kind in _TEXT_TYPES or kind.startswith("text/") or kind.endswith(("+xml", "/xml"))
    if (el.get("src") is not None or not textual) and entry.find(_a("summary")) is None:
        out.append(f"{where}: content with a src or in Base64 needs an atom:summary")


def _check_person(el: ET.Element, where: str, out: list[str]) -> None:
    """RFC 4287 3.2: one atom:name, at most one atom:uri (an IRI) and at most one atom:email."""
    if len(el.findall(_a("name"))) != 1:
        out.append(f"{where}: a person needs exactly one atom:name")
    for tag in ("uri", "email"):
        if len(el.findall(_a(tag))) > 1:
            out.append(f"{where}: more than one atom:{tag}")
    for uri in el.findall(_a("uri")):
        if not _ABSOLUTE_IRI.match((uri.text or "").strip()):
            out.append(f"{where}: atom:uri {uri.text!r} is not an absolute IRI")


def _check_links(parent: ET.Element, where: str, out: list[str]) -> None:
    alternates: set[tuple[str | None, str | None]] = set()
    for link in parent.findall(_a("link")):
        href = link.get("href")
        if not href:
            out.append(f"{where}: atom:link without href")
        elif not _ABSOLUTE_IRI.match(href):
            out.append(f"{where}: atom:link href {href!r} is not absolute")
        if link.get("rel", "alternate") == "alternate":
            key = (link.get("type"), link.get("hreflang"))
            if key in alternates:
                out.append(f"{where}: two alternate links with type {key[0]!r}")
            alternates.add(key)
    for cat in parent.findall(_a("category")):
        if not cat.get("term"):
            out.append(f"{where}: atom:category without term")
        scheme = cat.get("scheme")
        if scheme is not None and not _ABSOLUTE_IRI.match(scheme):
            out.append(f"{where}: atom:category scheme {scheme!r} is not an IRI")


def _one(parent: ET.Element, tag: str, where: str, out: list[str], required: bool = True) -> ET.Element | None:
    found = parent.findall(_a(tag))
    if len(found) > 1:
        out.append(f"{where}: {len(found)} atom:{tag} elements, at most one allowed")
    if required and not found:
        out.append(f"{where}: no atom:{tag}")
    return found[0] if found else None


def atom_problems(text: str, self_url: str | None = None) -> list[str]:
    """Every RFC 4287 rule this feed can break, checked with the standard library.

    Covers sections 3 and 4: one id, title and updated on the feed and on every entry, at most
    one of each single-valued element, an author on the feed or on every entry, unique entry ids,
    IRIs that are absolute, RFC 3339 dates, text constructs of a known type with balanced HTML,
    at most one alternate link per type, a term on every category, a summary when the content
    has a src, and an alternate link when an entry has no content."""
    out: list[str] = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        return [f"not well-formed XML: {exc}"]
    if root.tag != _a("feed"):
        return [f"root element is {root.tag}, not atom:feed"]

    for tag in ("id", "title", "updated"):
        _one(root, tag, "feed", out)
    for tag in ("subtitle", "icon", "logo", "rights", "generator"):
        _one(root, tag, "feed", out, required=False)
    fid = root.find(_a("id"))
    if fid is not None and not _ABSOLUTE_IRI.match((fid.text or "").strip()):
        out.append(f"feed: atom:id {fid.text!r} is not an absolute IRI")
    upd = root.find(_a("updated"))
    if upd is not None and not _is_rfc3339(upd.text):
        out.append(f"feed: atom:updated {upd.text!r} is not an RFC 3339 date")
    for tag in ("title", "subtitle", "rights"):
        el = root.find(_a(tag))
        if el is not None:
            _check_text_construct(el, f"feed atom:{tag}", out)
    _check_links(root, "feed", out)
    selfs = [l.get("href") for l in root.findall(_a("link")) if l.get("rel") == "self"]
    if self_url and selfs != [self_url]:
        out.append(f"feed: self link is {selfs}, expected [{self_url!r}]")
    feed_authors = root.findall(_a("author"))
    for a in feed_authors:
        _check_person(a, "feed author", out)

    entries = root.findall(_a("entry"))
    if not entries:
        out.append("feed: no entries")
    seen_ids: set[str] = set()
    for n, entry in enumerate(entries, 1):
        eid = entry.find(_a("id"))
        where = f"entry {n} ({(eid.text if eid is not None else None)!r})"
        for tag in ("id", "title", "updated"):
            _one(entry, tag, where, out)
        for tag in ("published", "summary", "content", "rights", "source"):
            _one(entry, tag, where, out, required=False)
        if eid is not None:
            value = (eid.text or "").strip()
            if not _ABSOLUTE_IRI.match(value):
                out.append(f"{where}: atom:id is not an absolute IRI")
            if value in seen_ids:
                out.append(f"{where}: atom:id repeats an earlier entry's")
            seen_ids.add(value)
        for tag in ("updated", "published"):
            el = entry.find(_a(tag))
            if el is not None and not _is_rfc3339(el.text):
                out.append(f"{where}: atom:{tag} {el.text!r} is not an RFC 3339 date")
        for tag in ("title", "summary", "rights"):
            el = entry.find(_a(tag))
            if el is not None:
                _check_text_construct(el, f"{where} atom:{tag}", out)
        _check_links(entry, where, out)
        authors = entry.findall(_a("author"))
        for a in authors:
            _check_person(a, f"{where} author", out)
        source = entry.find(_a("source"))
        source_has_author = source is not None and source.find(_a("author")) is not None
        if not feed_authors and not authors and not source_has_author:
            out.append(f"{where}: no atom:author on the entry, its source or the feed")
        content = entry.find(_a("content"))
        if content is None:
            if not any(l.get("rel", "alternate") == "alternate" for l in entry.findall(_a("link"))):
                out.append(f"{where}: no atom:content and no alternate link")
        else:
            _check_content(content, entry, f"{where} atom:content", out)
    return out


# Every key JSON Feed 1.1 defines. `author` is the 1.0 key that 1.1 keeps readable.
_ITEM_KEYS = {"id", "url", "external_url", "title", "content_html", "content_text", "summary",
              "image", "banner_image", "date_published", "date_modified", "authors", "author",
              "tags", "language", "attachments"}
_FEED_KEYS = {"version", "title", "home_page_url", "feed_url", "description", "user_comment",
              "next_url", "icon", "favicon", "authors", "author", "language", "expired", "hubs",
              "items"}
# JSON Feed 1.1: an extension name is an underscore, a letter, and no dot.
_EXT_NAME = re.compile(r"^_[A-Za-z][^.]*$")


def _check_authors(authors: Any, where: str, out: list[str]) -> None:
    if not isinstance(authors, list) or not authors:
        out.append(f"{where}: authors must be a non-empty array")
        return
    for a in authors:
        if not isinstance(a, dict) or not any(isinstance(a.get(k), str) for k in ("name", "url", "avatar")):
            out.append(f"{where}: an author needs a name, url or avatar")


def json_feed_problems(text: str, feed_url: str | None = None) -> list[str]:
    """The JSON Feed 1.1 rules: required fields, types, unique item ids, RFC 3339 dates, and
    extension names that start with an underscore and a letter."""
    out: list[str] = []
    try:
        feed = json.loads(text)
    except ValueError as exc:
        return [f"not JSON: {exc}"]
    if not isinstance(feed, dict):
        return ["the top level is not an object"]
    if feed.get("version") != JSON_FEED_VERSION:
        out.append(f"version is {feed.get('version')!r}, expected {JSON_FEED_VERSION!r}")
    if not isinstance(feed.get("title"), str) or not feed["title"]:
        out.append("feed: title is required")
    # JSON Feed asks for URLs. That they are https is this site's own rule.
    for key in ("home_page_url", "feed_url", "icon", "favicon", "next_url"):
        if key in feed and not (isinstance(feed[key], str) and feed[key].startswith("https://")):
            out.append(f"feed: {key} must be an https URL")
    for key, kind in (("description", str), ("user_comment", str), ("language", str),
                      ("expired", bool), ("hubs", list)):
        if key in feed and not isinstance(feed[key], kind):
            out.append(f"feed: {key} must be a {kind.__name__}")
    if feed_url and feed.get("feed_url") != feed_url:
        out.append(f"feed: feed_url is {feed.get('feed_url')!r}, expected {feed_url!r}")
    if "authors" in feed:
        _check_authors(feed["authors"], "feed", out)
    for key in feed:
        if key not in _FEED_KEYS and not _EXT_NAME.match(key):
            out.append(f"feed: unknown key {key!r} (an extension must start with _ and a letter)")
    items = feed.get("items")
    if not isinstance(items, list):
        return out + ["feed: items must be an array"]
    if not items:
        out.append("feed: no items")
    seen: set[str] = set()
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            out.append(f"item {n}: not an object")
            continue
        iid = item.get("id")
        where = f"item {n} ({iid!r})"
        if not isinstance(iid, str) or not iid:
            out.append(f"{where}: id must be a non-empty string")
        elif iid in seen:
            out.append(f"{where}: id repeats an earlier item's")
        else:
            seen.add(iid)
        if not any(isinstance(item.get(k), str) and item[k] for k in ("content_html", "content_text")):
            out.append(f"{where}: needs content_html or content_text")
        if isinstance(item.get("content_html"), str):
            out += [f"{where} content_html: {f}" for f in html_fragment_problems(item["content_html"])]
        for key in ("url", "external_url", "image", "banner_image"):
            if key in item and not (isinstance(item[key], str) and item[key].startswith("https://")):
                out.append(f"{where}: {key} must be an https URL")
        for key in ("title", "summary", "language", "content_html", "content_text"):
            if key in item and not isinstance(item[key], str):
                out.append(f"{where}: {key} must be a string")
        for att in item.get("attachments", []) if isinstance(item.get("attachments", []), list) else [None]:
            if not (isinstance(att, dict) and isinstance(att.get("url"), str)
                    and isinstance(att.get("mime_type"), str)):
                out.append(f"{where}: an attachment needs a url and a mime_type")
        for key in ("date_published", "date_modified"):
            if key in item and not _is_rfc3339(item[key]):
                out.append(f"{where}: {key} {item[key]!r} is not an RFC 3339 date")
        if "tags" in item and not (isinstance(item["tags"], list)
                                   and all(isinstance(t, str) for t in item["tags"])):
            out.append(f"{where}: tags must be an array of strings")
        if "authors" in item:
            _check_authors(item["authors"], where, out)
        for key in item:
            if key not in _ITEM_KEYS and not _EXT_NAME.match(key):
                out.append(f"{where}: unknown key {key!r} (an extension must start with _ and a letter)")
    return out


_ARTICLE_RX = re.compile(
    r'<article id="v(?P<ver>[^"]+)"><h2>(?P<shown_ver>[^<]*) <time datetime="(?P<date>[^"]+)">'
    r'(?P<shown_date>[^<]*)</time></h2>\n(?P<body>.*?)</article>', re.S)


def _uncommented(page_html: str) -> str:
    """The page without HTML comments: markup inside one is not on the page."""
    return re.sub(r"<!--.*?-->", "", page_html, flags=re.S)


def page_entries(page_html: str) -> list[tuple[str, str, str]]:
    """(version, date, body html) for every dated <article> on changelog.html, in page order.
    An article whose heading shows another version or date than its anchor and its datetime
    is left out, so the parity check reports it."""
    return [(m["ver"], m["date"], m["body"]) for m in _ARTICLE_RX.finditer(_uncommented(page_html))
            if html.unescape(m["shown_ver"]) == m["ver"] and m["shown_date"] == m["date"]]


class _BlockText(HTMLParser):
    """The visible text of each <h3>, <li> and <p> in an article body, in order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self._open: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("h3", "li", "p"):
            self._open, self._text = tag, []

    def handle_endtag(self, tag: str) -> None:
        if tag == self._open:
            self.blocks.append((tag, " ".join("".join(self._text).split())))
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open:
            self._text.append(data)


def _page_sections(body: str) -> list[dict[str, Any]]:
    """What a reader of changelog.html sees in one entry, as sections of items and notes."""
    p = _BlockText()
    p.feed(body)
    sections: list[dict[str, Any]] = []
    for tag, text in p.blocks:
        if tag == "h3":
            words = text.split()
            sections.append({"name": words[0].rstrip(":") if words else None, "items": [], "notes": []})
            continue
        if not sections:
            sections.append({"name": None, "items": [], "notes": []})
        sections[-1]["items" if tag == "li" else "notes"].append(text)
    return sections


def parity_problems(page_html: str, atom_text: str, json_text: str, page_url: str) -> list[str]:
    """Every entry on changelog.html is in both feeds, in the same order, with the same version,
    date and body, and the two feeds agree with each other.

    The body is compared as HTML. The parsed fields of the JSON Feed (sections, items, notes)
    are compared with the text a reader sees on the page, read back from the page's HTML, so a
    parse that drops, splits or garbles an item shows here. Any difference is drift, whichever
    side it is on."""
    out: list[str] = []
    page = page_entries(page_html)
    if not page:
        return ["changelog.html: no dated <article> found"]
    if _uncommented(page_html).count("<article ") != len(page):
        out.append("changelog.html: an <article> does not have the id, heading and time shape")
    root = ET.fromstring(atom_text.encode("utf-8"))
    entries = root.findall(_a("entry"))
    items = json.loads(json_text)["items"]
    if len(entries) != len(page):
        out.append(f"atom has {len(entries)} entries, changelog.html has {len(page)}")
    if len(items) != len(page):
        out.append(f"json feed has {len(items)} items, changelog.html has {len(page)}")
    for (ver, date, body), e, j in zip(page, entries, items):
        want_id = f"{page_url}#v{ver}"
        stamp = f"{date}T00:00:00Z"
        content = e.find(_a("content"))
        alternates = [l.get("href") for l in e.findall(_a("link")) if l.get("rel", "alternate") == "alternate"]
        if (e.findtext(_a("id")), e.findtext(_a("published")), e.findtext(_a("updated")),
                content.text if content is not None else None, alternates) != (
                want_id, stamp, stamp, body, [want_id]):
            out.append(f"atom entry for {ver} differs from changelog.html (id, dates, link or content)")
        if content is None or content.get("type") != "html":
            out.append(f"atom entry for {ver}: content is not type html")
        if "content_text" in j:
            out.append(f"json feed item for {ver}: content_text would be a second account of the entry")
        ext = j.get(EXT_KEY, {})
        if (j.get("id"), j.get("url"), j.get("date_published"), j.get("content_html"),
                ext.get("version"), ext.get("date")) != (want_id, want_id, stamp, body, ver, date):
            out.append(f"json feed item for {ver} differs from changelog.html (id, url, date or content)")
        if ext.get("sections") != _page_sections(body):
            out.append(f"json feed item for {ver}: sections, items or notes differ from what changelog.html shows")
        title, summary = e.findtext(_a("title")) or "", e.findtext(_a("summary")) or ""
        if not title.startswith(f"{ver}: ") or not summary:
            out.append(f"atom entry for {ver}: title does not open with the version, or no summary")
        if (title, summary) != (j.get("title"), j.get("summary")):
            out.append(f"{ver}: the feeds disagree on title or summary")
        plain_cats = [c.get("term") for c in e.findall(_a("category")) if c.get("scheme") is None]
        client_cats = [c.get("term") for c in e.findall(_a("category")) if c.get("scheme") is not None]
        names = [s["name"] for s in _page_sections(body) if s["name"]]
        if plain_cats != j.get("tags") or plain_cats != list(dict.fromkeys(names)):
            out.append(f"{ver}: categories, tags and the page's section headings disagree")
        clients = [f"{c.get('client')} {c.get('version')}" for c in ext.get("client_libraries", [])]
        if client_cats != clients:
            out.append(f"{ver}: the feeds disagree on client library versions")
    return out


def alternate_links(page_html: str) -> list[dict[str, str]]:
    """The rel="alternate" feed links in a page's head, as attribute dicts."""
    head = _uncommented(page_html).split("</head>", 1)[0]
    links = []
    for tag in re.findall(r"<link\b[^>]*>", head):
        attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', tag))
        if attrs.get("rel") == "alternate" and attrs.get("type") in (
                "application/atom+xml", "application/feed+json"):
            links.append({k: html.unescape(v) for k, v in attrs.items()})
    return links


def names_for_clients(clients: Iterable[dict[str, Any]],
                      languages: dict[str, list[str]]) -> dict[str, tuple[str, str, str]]:
    """How the changelog writes each client -> (client name, package, newest published version).

    A language client is named by its language ("Python 1.8.0", "JS 1.10.2"). Every other
    package is named by its package name ("livetennisapi-ai 1.3.0") or by the name the client
    libraries page gives it ("MCP server 1.6.5")."""
    out: dict[str, tuple[str, str, str]] = {}
    for c in clients:
        spoken = languages.get(c["key"])
        if spoken:
            for word in spoken:
                out[word] = (spoken[0], c["package"], c["version"])
        else:
            for word in (c["package"], c["name"]):
                out[word] = (c["package"], c["package"], c["version"])
    return out
