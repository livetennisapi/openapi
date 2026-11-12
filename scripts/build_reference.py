#!/usr/bin/env python3
"""Generate a fully server-rendered HTML reference from ``openapi.yaml``.

Why this exists
---------------
The interactive reference (Scalar) renders client-side. **No major AI crawler
executes JavaScript** — GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot,
Claude-SearchBot, PerplexityBot and Bytespider all read the raw HTML response
only; Gemini is the sole exception. Measured against the deployed site,
``curl -A GPTBot https://docs.livetennisapi.com/`` returned **22 characters**
("Loading API reference…") and zero occurrences of ``/matches``,
``win_probability`` or any tier name.

So the canonical API reference was invisible to every answer engine. This
generator emits the same content as plain HTML — every endpoint, parameter,
response schema, tier annotation and error code as real text in the source —
so an engine that never runs a line of JavaScript can still read, index and
cite the whole API.

It is generated rather than hand-written so it cannot drift from the spec: it
runs in CI on every push, from the same ``openapi.yaml`` the SDKs are built
against.

Usage:
    python scripts/build_reference.py            # writes docs/reference.html + docs/llms.txt
    python scripts/build_reference.py --check    # verify output is current (CI)
"""

from __future__ import annotations

import argparse
import json
import html
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "openapi.yaml"
DOCS = ROOT / "docs"
SITE = "https://livetennisapi.com"
DOCS_URL = "https://docs.livetennisapi.com"
# Footer credit on every generated page. Synapse Research Ltd builds and runs the API.
CREDIT = ('<p class="meta">Built by <a href="https://synapsereality.io/work/live-tennis-api/">'
          'Synapse Research Ltd</a>.</p>')
# The publisher node on every page. It carries the same @id as the apex page's Organization so
# the two nodes merge into one entity, and the same profiles: Ahrefs flagged the docs'
# Organization as incomplete while it had only name, url and logo and the apex had the brand
# name and sameAs. Keep this list and livetennisapi.com's in step.
# Registry pages per package, and the organisation that hosts the source.
GITHUB_ORG_URL = "https://github.com/livetennisapi"
PYPI_URL = "https://pypi.org/project/livetennisapi/"
NPM_JS_URL = "https://www.npmjs.com/package/livetennisapi"
NPM_MCP_URL = "https://www.npmjs.com/package/livetennisapi-mcp"
CONTACT_EMAIL = "hello@livetennisapi.com"
ORG_SAMEAS = [
    "https://rapidapi.com/contact-whTqTESH5/api/tennis-data-analytics-api3",
    "https://apify.com/livetennisapi/tennis-data-analytics",
    "https://api.market/store/live-tennis-api/tennis-data-analytics",
    "https://www.postman.com/livetennisapi",
    GITHUB_ORG_URL,
    PYPI_URL,
    NPM_JS_URL,
    NPM_MCP_URL,
    DOCS_URL,
    "https://x.com/livetennisapi",
]
ORG_NODE = {"@type": "Organization", "@id": f"{SITE}/#org", "name": "JSB Holdings LLC",
            "alternateName": "Live Tennis API", "url": SITE, "logo": f"{DOCS_URL}/icon-256.png",
            "sameAs": ORG_SAMEAS}


def tech_article_ld(headline: str, description: str, url: str, **extra: Any) -> str:
    """The TechArticle JSON-LD block every docs page carries, serialized once from a dict.

    JSON-LD is JSON inside a script element: the browser hands the parser the raw text, so an
    HTML entity in it is never decoded. The topic pages used to format this block with E() and
    shipped the literal text player&#x27;s in a description while the meta tag decoded to
    player's. json.dumps writes the string as JSON; the one escape that matters is "</", which
    would otherwise close the script element early. `extra` keeps the dict's key order after url
    (dateModified, about), so the four templates emit the same shape."""
    node: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": headline,
        "description": description,
        "url": url,
        **extra,
        "inLanguage": "en",
        "isPartOf": {"@type": "WebSite", "name": "Live Tennis API", "url": SITE},
        "publisher": ORG_NODE,
    }
    return json.dumps(node, ensure_ascii=False).replace("</", "<\\/")


# Result-page budgets. A <title> past 60 characters and a description past 155 are cut in the
# result; a description under 110 leaves the snippet half empty. main() refuses a page outside
# them, index.html included.
TITLE_MAX = 60
DESC_MIN, DESC_MAX = 110, 155
# Words a description must not end on when the budget cuts it mid-sentence.
DANGLING = {"a", "an", "and", "as", "at", "by", "for", "from", "get", "post", "in", "is", "of",
            "on", "or", "so", "the", "then", "to", "with"}


def site_navigation(active: str) -> str:
    """Shared, server-rendered navigation for every documentation page."""
    destinations = [
        ("index", "./", "Overview"),
        ("reference", "./reference.html", "API reference"),
        ("changelog", "./changelog.html", "Changelog"),
    ]
    links = "".join(
        f'<a href="{href}"' + (' aria-current="page"' if key == active else '')
        + f'>{label}</a>' for key, href, label in destinations
    )
    topics = "".join(
        f'<a href="./{t["slug"]}.html"'
        + (' aria-current="page"' if t["slug"] == active else '')
        + f'>{E(t["title"])}</a>' for t in TOPICS + GUIDES
    )
    return (
        '<header class="docs-site-header"><a class="docs-brand" href="./">'
        '<img src="logo.svg" width="28" height="28" alt="">'
        'Live Tennis API <span>Docs</span></a>'
        '<nav class="docs-desktop-nav" aria-label="Documentation">' + links + '</nav>'
        '<a class="docs-key" href="https://livetennisapi.com/subscribe/free">Get a free key '
        '<span aria-hidden="true">↗</span></a></header>'
        '<details class="docs-topic-menu"><summary>Explore the documentation</summary>'
        '<nav aria-label="Documentation topics">' + links + topics + '</nav></details>'
    )


# Inlined below (INLINE_STYLES / DESIGN_STYLES): see the note above _inline_css.

# --- design tokens ----------------------------------------------------------
# Mirrored from the product's canonical palette (app/services/design_tokens.py
# in the application repo). This repo is published separately and cannot import
# it, so the values are restated here rather than re-invented: keep them in step
# with that module, which is the source of truth.
#
# Contrast is part of the contract. Every pairing rendered below is >= 4.5:1 for
# text under 18px, measured against the surface the text actually sits on:
#   TEXT   on BG    14.95:1     MUTED on BG     6.11:1
#   TEXT   on PANEL 14.27:1     MUTED on PANEL  5.83:1
#   OURS   on BG    14.14:1     MUTED on STRUCT 4.54:1
# The recede tier (#5a6675, 3.30:1 on BG) is deliberately not used here: this
# page has no text at 18px or above outside the headings.
BG = "#0e0e0e"
PANEL = "#141414"
STRUCT = "#2a2a2a"
TEXT = "#e4e2e1"
MUTED = "#84967e"
OURS = "#00ff41"
R_CONTROL = "6px"

# Which plan unlocks which endpoint. The spec encodes this in prose summaries
# ("(PRO)"), so it is parsed from there rather than duplicated by hand.
TIER_ORDER = {"BASIC": 0, "PRO": 1, "ULTRA": 2}


# ---------------------------------------------------------------- spec helpers


# Fonts the page needs BEFORE first paint, preloaded so they cannot swap in afterwards.
#
# Every face is declared font-display: swap, and only Inter 400 was preloaded — so the h1's
# Space Grotesk and the base-URL <code>'s JetBrains Mono arrived after the header had already
# been laid out, the header changed height, and everything below it moved. Measured on
# live-scores.html: desktop CLS 0.237 in 3 of 4 PageSpeed runs, with the whole <main> named as
# the shifting element. The 4th run read 0.000, which is why one reading is not a measurement.
#
# Preloading is the right lever rather than font-display:optional, which would fix CLS by not
# showing the display face at all on a first visit.
# The two text faces fetch at high priority: they are what the h1 and the first paragraph, the
# largest text above the fold, wait for. Mono stays preloaded (the base-URL <code> in the header
# would otherwise move the page when it arrived) but queues behind them rather than beside them.
FONT_PRELOADS = "".join(
    f'<link rel="preload" href="fonts/{f}.woff2" as="font" type="font/woff2" crossorigin fetchpriority="{pr}">\n'
    for f, pr in (("inter-latin-400", "high"), ("space-grotesk-latin-700", "high"),
                  ("jetbrains-mono-latin-400", "low"))
)

# fonts.css and the shared design stylesheet are inlined into every generated page instead of
# being linked. Both are small (2.3 KB and 10 KB), and as <link>s they were two render-blocking
# requests discovered only after the whole document had arrived: on PageSpeed's slow-4G mobile
# profile reference.html (131 KB over the wire) painted at 1.8 s and the h1 settled at 2.85 s,
# over the 2.5 s LCP budget (launch acceptance R1.6, 2026-10-06). Inlined, the first paint needs
# nothing beyond the document and the preloaded fonts. The files stay on disk for index.html,
# which Scalar styles, and for anything that still links them.
_DOCS = Path(__file__).resolve().parents[1] / "docs"


def _inline_css(name: str) -> str:
    return "<style>\n" + (_DOCS / name).read_text(encoding="utf-8").strip() + "\n</style>\n"


INLINE_STYLES = _inline_css("fonts.css")
DESIGN_STYLES = _inline_css("docs-design-20260918.css")


def reference_base_style(reference_html: str) -> str:
    """The reference's own base stylesheet (tokens, .wrap, .pagenav, .vh), for the pages that
    reuse its look. Since fonts.css was inlined the first <style> in reference.html is the font
    block, so "the first <style>" silently gave every topic page the fonts twice and no base
    rules: captions meant for screen readers showed on screen. Skip the shared blocks instead."""
    for block in re.findall(r"<style>.*?</style>\n?", reference_html, re.S):
        if block.strip() not in (INLINE_STYLES.strip(), DESIGN_STYLES.strip()):
            if ".vh" not in block:
                raise SystemExit("reference.html: base stylesheet not found (no .vh rule)")
            return block.rstrip("\n")
    raise SystemExit("reference.html: no base stylesheet found")

# The reference is one 36,000-word document with 95 <section>s and a header-to-footer run of
# tables. Chrome styled and laid out all of it before the first paint: 670 ms of style and
# layout on the PageSpeed mobile profile, most of it for content far below the fold. With
# content-visibility:auto a section is laid out when it comes into view (anchor links and
# find-in-page still reach it), and contain-intrinsic-size keeps the scrollbar honest.
SECTION_CSS = (
    "<style>\n  main section { content-visibility:auto; contain-intrinsic-size: auto 800px; }\n"
    "</style>\n"
)

# The first-party pageview beacon, shared by every generated page.
#
# The docs are a separate origin, so the apps' server-side visit log never sees a docs request —
# yet for a developer API the docs ARE the mid-funnel, and "did they read the docs before
# subscribing?" was unanswerable because of it. The lt_vid cookie is Domain=.livetennisapi.com,
# so this subdomain is same-site and the visit stitches into the same journey as the pricing page
# and checkout. Allowlisted kind, always 204, wrapped so it can never affect the page. Covered by
# the first-party visit log described at https://livetennisapi.com/privacy — no new cookie here.
#
# It lives here rather than inside the reference's template because it was inside that template,
# and the eight topic pages and the changelog were written later and silently got none of it.
# Nine of eleven docs pages were invisible the day the docs stopped being three pages.
BEACON = (
    "<script>\n"
    "(function(){try{navigator.sendBeacon('https://livetennisapi.com/collect',"
    "JSON.stringify({kind:'docs_view',path:location.pathname,host:location.host}))}catch(e){}})();"
    "\n</script>\n"
)

# Clarity, EU/EEA-gated. The beacon above says a page was LOADED; it cannot see scroll depth,
# rage clicks, dead clicks or quick-backs, which on a reference page is most of what "did this
# answer the question?" means. The docs were the last surface with no on-page behaviour data.
#
# ONLY Clarity. Deliberately not PostHog (autocapture puts URLs into a third-party tool and is
# not geo-gated — it is what leaked 2,509 credential-bearing URLs on the apex) and not Google
# Ads (nothing converts on a docs page, so a remarketing tag would be cost without signal).
#
# THE GATE. This host is GitHub Pages, not Cloudflare, so there is no local /cdn-cgi/trace — it
# 404s. The apex one is fetched cross-origin instead, which works because Cloudflare answers it
# with `access-control-allow-origin: *`. It FAILS CLOSED, unlike the apex copy in tennis
# app/routes/landing.py: an unreadable or unmatched `loc` loads nothing, because a cross-origin
# fetch has more ways to return something unexpected than a same-origin one, and the wrong
# default here is the one that tags an EU visitor. Matches https://livetennisapi.com/privacy.
#
# Interpolated as {CLARITY} the same way as {BEACON}. Both are plain strings, NOT f-strings, so
# the braces in the JS below stay single here — it is only JS written directly inside a
# template's f-string that needs them doubled.
CLARITY = (
    "<script>\n"
    '(function(){var E={};"AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT '
    'RO SK SI ES SE IS LI NO".split(" ").forEach(function(c){E[c]=1});'
    'fetch("https://livetennisapi.com/cdn-cgi/trace").then(function(r){return r.text()})'
    '.then(function(t){var m=t.match(/loc=(\\w+)/);if(!m||E[m[1]])return;'
    '(function(c,l,a,r,i,t,y){c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};'
    't=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;'
    'y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y)})'
    '(window,document,"clarity","script","xotc2pctsp");'
    'try{clarity("set","user_state","docs")}catch(e){}}).catch(function(){})})();'
    "\n</script>\n"
)


def load_spec() -> dict[str, Any]:
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))


def resolve(node: Any, spec: dict[str, Any], _seen: frozenset[str] = frozenset()) -> Any:
    """Inline ``$ref`` pointers so the rendered page contains real field names.

    Guards against a self-referential schema by tracking the refs already
    expanded on this branch; a cycle renders as a named placeholder rather than
    recursing forever.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            if ref in _seen:
                return {"_cycle": ref.rsplit("/", 1)[-1]}
            target: Any = spec
            for part in ref[2:].split("/"):
                target = target.get(part, {}) if isinstance(target, dict) else {}
            merged = resolve(target, spec, _seen | {ref})
            rest = {k: resolve(v, spec, _seen) for k, v in node.items() if k != "$ref"}
            if isinstance(merged, dict):
                # `_ref` keeps the component's name after inlining, so a field
                # table can name and link the schema instead of saying "object".
                name = ref.rsplit("/", 1)[-1] if ref.startswith("#/components/schemas/") else None
                return {**merged, **({"_ref": name} if name else {}), **rest}
            return merged
        return {k: resolve(v, spec, _seen) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve(v, spec, _seen) for v in node]
    return node


def tier_of(summary: str) -> str:
    """Read the plan out of the operation summary, e.g. '… (PRO)' -> 'PRO'.

    The FIRST tier named is the plan that unlocks the endpoint; later mentions
    are embed upsells ("(FREE; +market PRO, +analysis ULTRA)"). The old
    highest-tier-wins scan labelled that summary ULTRA — telling a FREE user
    the match-detail endpoint was locked four tiers up — and did not know FREE
    existed at all, so every FREE endpoint rendered "Plan required: —".
    """
    hits = [(summary.find(t), t) for t in ("FREE", "BASIC", "PRO", "ULTRA")
            if summary and t in summary]
    return min(hits)[1] if hits else "—"


def type_of(schema: dict[str, Any]) -> str:
    """Render a JSON Schema type as compact human text."""
    if not isinstance(schema, dict):
        return "—"
    if "_cycle" in schema:
        return schema["_cycle"]
    if schema.get("_ref") and _is_object(schema):
        return schema["_ref"]
    for combinator in ("oneOf", "anyOf", "allOf"):
        if combinator in schema:
            parts = [type_of(s) for s in schema[combinator] if isinstance(s, dict)]
            parts = [p for p in parts if p and p != "—"]
            return " or ".join(dict.fromkeys(parts)) or "object"
    t = schema.get("type")
    if isinstance(t, list):
        t = " or ".join(str(x) for x in t)
    if t == "array":
        return f"array of {type_of(schema.get('items', {}))}"
    if schema.get("enum"):
        allowed = ", ".join("null" if e is None else str(e) for e in schema["enum"])
        return f"{t or 'string'} ({allowed})"
    if t == "object" and schema.get("properties"):
        return "object"
    extra = schema.get("additionalProperties")
    if isinstance(extra, dict) and extra and not schema.get("properties"):
        return f"map of {type_of(extra)}"
    return str(t or "object")


def _is_object(schema: dict[str, Any]) -> bool:
    t = schema.get("type")
    return (t == "object" or (isinstance(t, list) and "object" in t)
            or "properties" in schema or "allOf" in schema)


def _own_props(schema: dict[str, Any]) -> dict[str, Any]:
    """Properties of a schema, with ``allOf`` branches merged in."""
    props: dict[str, Any] = {}
    for branch in schema.get("allOf", []):
        if isinstance(branch, dict) and isinstance(branch.get("properties"), dict):
            props.update(branch["properties"])
    if isinstance(schema.get("properties"), dict):
        props.update(schema["properties"])
    return props


def _refs_of(schema: dict[str, Any]) -> list[str]:
    """Component names a field's type points at: the schema itself, an array's items,
    or a ``oneOf``/``anyOf`` branch (``Player or null``)."""
    if not isinstance(schema, dict):
        return []
    if schema.get("_ref"):
        return [schema["_ref"]]
    if "_cycle" in schema:
        return [schema["_cycle"]]
    out: list[str] = []
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            out += _refs_of(schema[key])
    for combinator in ("allOf", "oneOf", "anyOf"):
        for branch in schema.get(combinator, []):
            out += _refs_of(branch)
    return list(dict.fromkeys(out))


def _inline_children(schema: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """The nested object to expand under a field, with the path suffix it takes.

    Only INLINE objects expand. A named component keeps one row that links to its own
    schema table, so the tables stay readable and a component reached from many fields
    is described once. Map values (``additionalProperties``) expand as ``.*``.
    """
    if schema.get("_ref") or "_cycle" in schema:
        return None
    branches = [b for b in schema.get("allOf", []) if isinstance(b, dict)]
    if (branches and not isinstance(schema.get("properties"), dict)
            and all(b.get("_ref") or "_cycle" in b for b in branches)):
        return None  # `allOf: [$ref]` beside a description: still the named component
    if _own_props(schema):
        return "", schema
    for combinator in ("oneOf", "anyOf"):
        objs = [b for b in schema.get(combinator, [])
                if isinstance(b, dict) and _own_props(b) and not b.get("_ref")]
        if len(objs) == 1:
            return "", objs[0]
    items = schema.get("items")
    if isinstance(items, dict) and not items.get("_ref") and _own_props(items):
        return "[]", items
    extra = schema.get("additionalProperties")
    if isinstance(extra, dict) and not extra.get("_ref") and _own_props(extra):
        return ".*", extra
    return None


#: Deepest nesting a field table spells out. The deepest inline path in the spec is
#: four levels (records.sets.sample.excluded.retired); past the cap a row stops at its type.
FIELD_DEPTH_MAX = 6


def fields_of(schema: dict[str, Any]) -> list[tuple[str, str, str, list[str]]]:
    """Flatten a schema's properties into (path, type, description, refs) rows.

    Merges ``allOf`` branches, so a composed schema like ``MatchDetail``
    (``Match`` + extra embeds) renders its full field set rather than nothing.
    Nested inline objects are walked recursively and named by dotted path
    (``records.sets.tiebreaks.won``; ``recent[].date`` for array items). A field
    whose type is a named component is not expanded: ``refs`` names it so the
    renderer can link to that component's own table. The walk stops at
    ``FIELD_DEPTH_MAX`` and at any object it is already inside (YAML aliases can
    make a shared node reachable from itself).
    """
    rows: list[tuple[str, str, str, list[str]]] = []

    def walk(node: dict[str, Any], prefix: str, depth: int, inside: frozenset[int]) -> None:
        for name, sub in _own_props(node).items():
            if not isinstance(sub, dict):
                continue
            path = f"{prefix}{name}"
            rows.append((path, type_of(sub), sub.get("description", ""), _refs_of(sub)))
            nested = _inline_children(sub)
            if nested is None or depth + 1 >= FIELD_DEPTH_MAX:
                continue
            suffix, child = nested
            if id(child) in inside:
                continue
            walk(child, f"{path}{suffix}.", depth + 1, inside | {id(child)})

    if isinstance(schema, dict):
        walk(schema, "", 0, frozenset({id(schema)}))
    return rows


def type_cell(text: str, refs: list[str], href_prefix: str = "#") -> str:
    """The escaped type text, with each named component linked to its schema table."""
    out = E(text)
    for ref in refs:
        out = re.sub(
            rf"(?<![\w-]){re.escape(E(ref))}(?![\w-])",
            f'<a href="{href_prefix}schema-{E(ref.lower())}">{E(ref)}</a>',
            out,
            count=1,
        )
    return out


# ------------------------------------------------------------------ rendering

E = html.escape


def md_inline(text: str) -> str:
    """Minimal markdown: backtick code and bare URLs, escaped first.

    The bare-URL half of that promise was never implemented, which is why the
    spec's own FREE-signup URL rendered as dead plain text — the one link in the
    description a reader most wants to click. Autolinking happens after escaping
    and skips anything already inside a tag, so it cannot produce nested markup.

    Running after escaping is what makes the URL body fiddly. By the time this
    regex sees the text there are no literal `<` or `>` left to stop at: a
    Markdown autolink written `<https://example.com/x>` has already become
    `&lt;https://example.com/x&gt;`, so a class that merely excludes `<>` runs
    straight through the closing entity and emits
    `href="https://example.com/x&gt"` with a stray `;` after the anchor. That
    shipped — Ahrefs found it on docs/changelog.html 2026-09-16 as a 303 to
    `/subscribe/free&gt`. So the body stops at a bare `&` and `&amp;` is spelled
    out as the one entity allowed through, because that is what a real query
    separator looks like once escaped (`?a=1&b=2` -> `?a=1&amp;b=2`).
    """
    out = E(text or "")
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    # Trailing punctuation is sentence punctuation, not part of the URL.
    body = r"(?:&amp;|[^\s<>()\"'&])"          # any URL char, or an escaped query separator
    last = r"(?:&amp;|[^\s<>()\"'&.,;:])"      # ...that is not sentence punctuation
    out = re.sub(
        rf"(?<![\"'=>])(https?://{body}+{last})",
        r'<a href="\1">\1</a>',
        out,
    )
    return out


def vh_caption(text: str) -> str:
    """A caption naming the table for screen readers.

    48 tables shipped with no caption and 155 <th> with no scope. A caption is
    the only thing that tells a screen-reader user WHICH operation a bare
    "Field / Type / Description" grid belongs to, since the heading above it is
    just the word "Parameters". Visually hidden: the visible <h4> already says
    it, so showing it twice would only add noise.
    """
    return f'<caption class="vh">{E(text)}</caption>'


def scrollx(inner: str, label: str) -> str:
    """Wrap a wide block in a keyboard-reachable horizontal scroll region.

    The scrolling used to live on the <table> itself (``display:block;
    overflow-x:auto``). That contained the tables correctly, but a scroll
    container reachable only by dragging is invisible to a keyboard, and
    ``display:block`` is not how a table wants to lay out. Moving the overflow
    onto a wrapper with ``role=region`` + ``tabindex=0`` is the standard
    pattern: the region is focusable and arrow-scrollable, the table goes back
    to being a table, and the CSS can hang a visible "scroll" affordance off
    the wrapper for touch users.
    """
    return f'<div class="scrollx" tabindex="0" role="region" aria-label="{E(label)}">{inner}</div>'


def render_schema_table(name: str, schema: dict[str, Any]) -> str:
    rows = fields_of(schema)
    if not rows:
        return ""
    body = "\n".join(
        f"<tr><td><code>{E(n)}</code></td><td>{type_cell(t, r)}</td><td>{md_inline(d)}</td></tr>"
        for n, t, d, r in rows
    )
    desc = md_inline(schema.get("description", ""))
    return (
        f'<section id="schema-{E(name.lower())}">\n'
        f"<h3>{E(name)}</h3>\n"
        + (f"<p>{desc}</p>\n" if desc else "")
        + '<div class="scrollx" tabindex="0" role="region" '
        f'aria-label="{E(name)} fields">'
        f"<table>{vh_caption(f'{name} schema — fields')}"
        '<thead><tr><th scope="col">Field</th><th scope="col">Type</th>'
        "<th scope=\"col\">Description</th></tr></thead>\n"
        f"<tbody>{body}</tbody></table></div>\n</section>"
    )


def render_operation(path: str, method: str, op: dict[str, Any], spec: dict[str, Any],
                     schema_href: str = "#") -> str:
    """One operation's section. ``schema_href`` prefixes schema links: ``#`` on
    reference.html, which holds the schema tables, ``./reference.html#`` elsewhere."""
    summary = op.get("summary", "")
    tier = tier_of(summary)
    op_id = op.get("operationId", "")
    anchor = op_id or f"{method}-{path}".strip("/").replace("/", "-")

    parts = [
        f'<section class="op" id="{E(anchor)}">',
        f'<h3><span class="method">{E(method.upper())}</span> <code>{E(path)}</code></h3>',
        f'<p class="summary">{md_inline(summary)}</p>',
        f'<p class="meta">Plan required: <strong>{E(tier)}</strong>'
        + (f' &middot; operationId: <code>{E(op_id)}</code>' if op_id else "")
        + "</p>",
    ]

    # The description is where an operation says WHICH plan unlocks what
    # (e.g. the History endpoints' live-API tier vs Historical Data API plan
    # mapping). Dropping it silently un-documented the tier deltas.
    description = op.get("description", "")
    if description:
        parts.append(f"<p>{md_inline(description)}</p>")

    params = [resolve(p, spec) for p in op.get("parameters", [])]
    if params:
        rows = []
        for p in params:
            if not isinstance(p, dict):
                continue
            sch = p.get("schema", {}) or {}
            default = sch.get("default")
            lo, hi = sch.get("minimum"), sch.get("maximum")
            notes = []
            if default is not None:
                notes.append(f"Default <code>{E(str(default))}</code>.")
            if lo is not None and hi is not None:
                notes.append(f"Range <code>{E(str(lo))}</code>&ndash;<code>{E(str(hi))}</code>.")
            elif lo is not None:
                notes.append(f"Minimum <code>{E(str(lo))}</code>.")
            elif hi is not None:
                notes.append(f"Maximum <code>{E(str(hi))}</code>.")
            extra = " " + " ".join(notes) if notes else ""
            rows.append(
                f"<tr><td><code>{E(str(p.get('name','')))}</code></td>"
                f"<td>{E(str(p.get('in','')))}</td>"
                f"<td>{E(type_of(sch))}</td>"
                f"<td>{'yes' if p.get('required') else 'no'}</td>"
                f"<td>{md_inline(p.get('description',''))}{extra}</td></tr>"
            )
        parts.append(
            "<h4>Parameters</h4>"
            + scrollx(
                f"<table>{vh_caption(f'{method.upper()} {path} — parameters')}"
                '<thead><tr><th scope="col">Name</th><th scope="col">In</th>'
                '<th scope="col">Type</th><th scope="col">Required</th>'
                '<th scope="col">Notes</th></tr></thead><tbody>'
                + "".join(rows)
                + "</tbody></table>",
                f"{method.upper()} {path} parameters",
            )
        )

    responses = op.get("responses", {})
    rows = []
    for code, resp in responses.items():
        resolved = resolve(resp, spec)
        desc = resolved.get("description", "") if isinstance(resolved, dict) else ""
        rows.append(f"<tr><td><code>{E(str(code))}</code></td><td>{md_inline(desc)}</td></tr>")
    if rows:
        parts.append(
            "<h4>Responses</h4>"
            + scrollx(
                f"<table>{vh_caption(f'{method.upper()} {path} — responses')}"
                '<thead><tr><th scope="col">Status</th>'
                '<th scope="col">Meaning</th></tr></thead>'
                "<tbody>" + "".join(rows) + "</tbody></table>",
                f"{method.upper()} {path} responses",
            )
        )

    ok = responses.get("200") or responses.get(200)
    if isinstance(ok, dict):
        schema = resolve(ok, spec).get("content", {}).get("application/json", {}).get("schema", {})
        rows = fields_of(schema)
        if not rows and isinstance(schema.get("properties", {}).get("data"), dict):
            rows = fields_of(schema["properties"]["data"].get("items", {}))
        if rows:
            body = "".join(
                f"<tr><td><code>{E(n)}</code></td><td>{type_cell(t, r, schema_href)}</td>"
                f"<td>{md_inline(d)}</td></tr>"
                for n, t, d, r in rows
            )
            parts.append(
                "<h4>Response fields</h4>"
                + scrollx(
                    f"<table>{vh_caption(f'{method.upper()} {path} — response fields')}"
                    '<thead><tr><th scope="col">Field</th><th scope="col">Type</th>'
                    '<th scope="col">Description</th></tr></thead><tbody>'
                    + body
                    + "</tbody></table>",
                    f"{method.upper()} {path} response fields",
                )
            )

    curl = f"curl {DOCS_URL and ''}{spec['servers'][0]['url']}{path}"
    parts.append(
        "<h4>Example</h4><pre><code>"
        + E(f"curl {spec['servers'][0]['url']}{path.replace('{matchId}', '18953').replace('{playerId}', '1104')}")
        + (" \\\n  -H &quot;Authorization: Bearer twjp_...&quot;" if path != "/health" else "")
        + "</code></pre>"
    )
    parts.append("</section>")
    return "\n".join(parts)


def build_html(spec: dict[str, Any]) -> str:
    info = spec["info"]
    base = spec["servers"][0]["url"]

    toc = []
    ops = []
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            op_id = op.get("operationId") or f"{method}-{path}"
            toc.append(
                f'<li><a href="#{E(op_id)}"><code>{E(method.upper())} {E(path)}</code>'
                f' — {E(op.get("summary",""))}</a></li>'
            )
            ops.append(render_operation(path, method, op, spec))

    schemas = spec.get("components", {}).get("schemas", {})
    schema_html = "\n".join(
        render_schema_table(name, resolve(s, spec)) for name, s in schemas.items()
    )

    description = md_inline(info.get("description", "")).replace("\n\n", "</p><p>")

    # Every topic page links back here; this is the link the other way, so neither is an
    # orphan and a crawler reaching either one reaches all of them.
    topic_nav = "\n".join(
        f'<a href="./{t["slug"]}.html">{E(t["title"])}</a>' for t in TOPICS + GUIDES
    )

    desc = ("Complete text reference for the Live Tennis API: every endpoint, parameter, "
            "response field and plan tier, for ATP, WTA, Challenger and ITF.")
    ld_json = tech_article_ld(f"{info['title']} — Full API Reference", desc,
                              f"{DOCS_URL}/reference.html")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(info['title'])} — Full API Reference (text)</title>
<meta name="description" content="{E(desc)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{DOCS_URL}/reference.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{E(info['title'])} — Full API Reference">
<meta property="og:url" content="{DOCS_URL}/reference.html">
<meta property="og:image" content="{DOCS_URL}/banner.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="favicon.ico" sizes="any">
<script type="application/ld+json">
{ld_json}
</script>
{FONT_PRELOADS}{INLINE_STYLES}
<style>
  /* Design tokens (app/services/design_tokens.py). This page used to carry the
     legacy marketing palette — every one of its six dark hexes was an exact key
     in design_tokens.LEGACY, i.e. a colour the token module exists to retire. */
  :root {{
    --bg:{BG}; --panel:{PANEL}; --struct:{STRUCT};
    --text:{TEXT}; --muted:{MUTED}; --accent:{OURS};
    --r:{R_CONTROL};           /* control radius; structure is square */
    color-scheme: dark;        /* was "normal", which invites the UA to
                                  render form controls and scrollbars light */
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
         font:16px/1.65 'Inter',ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }}
  .wrap {{ max-width:960px; margin:0 auto; padding:40px 20px 80px; }}

  /* PROSE MEASURE. The wrap is 960px because the tables and code blocks need
     it; running body text to that width gives ~110 characters a line, well past
     the 45-75 the eye tracks comfortably. Only the prose is narrowed — tables,
     pre and the endpoint sections keep the full width they need. */
  main > p, main > ul:not(.toc), main > ol, .op > p, .banner > p, header > p {{ max-width:72ch; }}

  a {{ color:var(--accent); }}
  a:focus-visible, .scrollx:focus-visible, .skip-link:focus {{
    outline:2px solid var(--accent); outline-offset:2px; }}
  h1,h2,h3 {{ font-family:'Space Grotesk','Inter',ui-sans-serif,sans-serif; }}
  h1 {{ font-size:2rem; margin:0 0 .3em; }}
  h2 {{ margin-top:2.5em; padding-bottom:.3em; border-bottom:1px solid var(--struct); }}
  h3 {{ margin-top:2em; }}
  h4 {{ margin:1.4em 0 .4em; color:var(--muted); font-size:.85rem; text-transform:uppercase; letter-spacing:.08em; }}
  code {{ background:var(--panel); padding:.15em .4em; border-radius:var(--r); font-size:.9em;
          font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace; }}
  pre {{ background:var(--panel); border:1px solid var(--struct); padding:14px; border-radius:0;
         overflow-x:auto; font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace; }}
  pre code {{ background:none; padding:0; }}

  /* A long URL is better wrapped than hidden behind a scrollbar: it stays
     copyable and every character is on screen. */
  pre.urls {{ white-space:pre-wrap; overflow-wrap:anywhere; }}

  /* An inline <code> cannot scroll — it is inline. A long token inside one
     (the /ws URL) pushed the whole document 44px wider than the viewport at
     390px, which is a horizontal scrollbar on the PAGE, not in a block. */
  code {{ overflow-wrap:anywhere; }}

  /* Wide blocks scroll in a focusable region rather than in the table itself,
     so a keyboard can reach them. */
  .scrollx {{ overflow-x:auto; max-width:100%; }}
  table {{ width:100%; border-collapse:collapse; margin:.6em 0 1.2em; }}
  th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--struct);
           vertical-align:top; font-size:.92rem; }}
  th {{ color:var(--muted); font-weight:600; }}

  /* Visually hidden, still announced. */
  .vh {{ position:absolute; width:1px; height:1px; margin:-1px; padding:0;
         overflow:hidden; clip:rect(0 0 0 0); clip-path:inset(50%); white-space:nowrap; border:0; }}

  .method {{ color:var(--accent); font-family:'JetBrains Mono',ui-monospace,monospace; }}
  .meta {{ color:var(--muted); font-size:.9rem; }}
  .summary {{ margin:.2em 0; }}
  .banner {{ background:var(--panel); border:1px solid var(--struct); border-left:3px solid var(--accent);
             padding:14px 18px; border-radius:0; margin:1.5em 0; }}
  ul.toc {{ list-style:none; padding:0; }}
  ul.toc li {{ border-bottom:1px solid var(--struct); }}

  /* NAVIGATION TOUCH TARGETS. These stacked links were 19px tall and 11-12px
     apart — the page's only chrome, and the hardest thing on it to hit. The two
     inline links inside prose sentences are deliberately left alone: WCAG 2.5.8
     exempts a link inline in a block of text, and padding them would break the
     line box around them. */
  ul.toc li a, .pagenav a, .footnav a {{
    display:flex; align-items:center; min-height:44px; padding:4px 2px; }}
  .pagenav, .footnav {{ display:flex; flex-wrap:wrap; gap:0 18px; margin:.4em 0; }}
  .skip-link {{ position:absolute; left:-9999px; top:0;
                background:var(--panel); color:var(--accent); padding:12px 16px;
                border:1px solid var(--struct); z-index:10; }}
  .skip-link:focus {{ left:8px; top:8px; }}

  /* THE TEACHING BLOCK. As a <pre> this was 62 columns wide and showed 35 of
     them at 390px — every annotation sliced mid-word, which is precisely the
     content a first-time reader needs most. As a two-column grid the alignment
     that makes it teach survives on a wide screen, and on a narrow one the
     explanation simply stacks under the code it explains. Nothing scrolls,
     nothing is cut. */
  .annot {{ display:grid; grid-template-columns:max-content 1fr; gap:2px 22px;
            background:var(--panel); border:1px solid var(--struct);
            padding:14px; margin:.6em 0 1.2em; overflow-x:auto; }}
  .annot dt {{ font-family:'JetBrains Mono',ui-monospace,monospace; font-size:.9em;
               white-space:pre; margin:0; }}
  .annot dd {{ margin:0; color:var(--muted); font-size:.9em; align-self:center; }}
  @media (max-width:600px) {{
    .annot {{ grid-template-columns:1fr; gap:0; }}
    .annot dt {{ margin-top:.7em; white-space:pre-wrap; overflow-wrap:anywhere; }}
    .annot dt:first-child {{ margin-top:0; }}
    .annot dd {{ padding-bottom:.2em; }}
  }}

  /* Link-only table cells are targets, not prose, so they get the full 44px.
     (The inline links inside sentences are left alone — see above.) */
  .linkrow a {{ display:inline-flex; align-items:center; min-height:44px; }}

  /* SCROLL, OR WRAP. On a phone the code blocks showed as little as 54% of
     their widest line, cut mid-token. Soft-wrapping them shows all of it, and
     costs nothing on copy: a soft wrap is not a newline, so a copied curl
     command is still byte-for-byte the command. Desktop has the room and keeps
     the original hard lines. A table cannot wrap, so tables still scroll. */
  @media (max-width:760px) {{
    pre {{ white-space:pre-wrap; overflow-wrap:anywhere; }}
  }}

  /* A horizontal scrollbar is invisible on touch until you already know it is
     there, and the design system has no gradients to fade an edge with. So the
     regions that genuinely still scroll get a scrollbar that is always drawn,
     in tokens, plus a note in words. */
  .scrollnote {{ display:none; color:var(--muted); font-size:.8rem; margin:-.4em 0 1em; }}
  @media (max-width:760px) {{
    .scrollnote {{ display:block; }}
    .scrollx {{ scrollbar-width:thin; scrollbar-color:var(--muted) var(--panel); }}
    .scrollx::-webkit-scrollbar {{ height:6px; -webkit-appearance:none; }}
    .scrollx::-webkit-scrollbar-track {{ background:var(--panel); }}
    .scrollx::-webkit-scrollbar-thumb {{ background:var(--muted); }}
  }}
</style>
{DESIGN_STYLES}{SECTION_CSS}</head>
<body class="docs-page docs-reference">
<a class="skip-link" href="#main">Skip to content</a>
{site_navigation('reference')}
<div class="wrap">

<header>
<h1>{E(info['title'])} — Full Reference</h1>
<p class="meta">Version {E(str(info.get('version','')))} &middot; OpenAPI {E(str(spec.get('openapi','')))}</p>
<nav class="pagenav" aria-label="Related pages">
<a href="./">Interactive reference</a>
<a href="./openapi.yaml">OpenAPI spec</a>
<a href="./changelog.html">Changelog</a>
<a href="{SITE}/pricing">Pricing</a>
<a href="{SITE}">livetennisapi.com</a>
</nav>

<nav class="pagenav" aria-label="By topic">
{topic_nav}
</nav>

<div class="banner">
<p><strong>This is the plain-text reference.</strong> It contains the same content as the
interactive documentation but requires no JavaScript, so it can be read by search engines,
answer engines and any HTTP client.</p>
</div>
</header>

<!-- Contents. There used to be one list, of the twelve endpoints, buried under
     the seventh of nine sections; the prose sections it sat below were not
     listed anywhere and eight of the nine headings had no id to link to. -->
<nav aria-labelledby="contents-heading">
<h2 id="contents-heading">Contents</h2>
<ul class="toc">
<li><a href="#quickstart">Quickstart — no code required</a></li>
<li><a href="#base-url">Base URL</a></li>
<li><a href="#authentication">Authentication</a></li>
<li><a href="#plans">Plans</a></li>
<li><a href="#clients">Official client libraries</a></li>
<li><a href="#mcp">MCP server</a></li>
<li><a href="#conventions">Conventions</a></li>
<li><a href="#endpoints">Endpoints</a> — all {len(toc)}, with parameters and responses</li>
<li><a href="#websocket">WebSocket feed (ULTRA)</a></li>
<li><a href="#faq">FAQ — plans and data depth</a></li>
<li><a href="#schemas">Schemas</a></li>
</ul>
</nav>

<main id="main">

<p>{description}</p>

<h2 id="quickstart">Quickstart — no code required</h2>
<p>Paste this into a browser, with your key on the end. That's the whole setup:
no install, no headers, works on a phone.</p>
<pre class="urls"><code>{E(base)}/matches?status=live&amp;token=YOUR_KEY</code></pre>
<p>You'll get every live match. Here is one, and how to read it:</p>
<dl class="annot">
<dt>"players": {{ "p1": {{ "name": "Chase Ferguson" }},
             "p2": {{ "name": "Scott Jones"    }} }}</dt>
<dd>who is playing</dd>
<dt>"sets":    [1, 0]</dt>
<dd>p1 leads one set to nil</dd>
<dt>"games":   [[6, 3], [4, 4]]</dt>
<dd>first list is p1, second is p2 — so 6-4 in the first set, 3-4 in the second</dd>
<dt>"points":  ["0", "0"]</dt>
<dd>the game in progress</dd>
<dt>"server":  1</dt>
<dd>p1 is serving (2 = p2)</dd>
</dl>
<p><strong>Every score array is player-major:</strong> the first list belongs to player 1,
the second to player 2. Once that clicks, the rest of the API reads the same way.</p>
<p>Two more you can click, swapping <code>21131</code> for any <code>id</code> from the list above:</p>
<pre class="urls"><code>{E(base)}/matches/21131?token=YOUR_KEY
{E(base)}/matches/21131/score?token=YOUR_KEY</code></pre>
<p>The same first call from a terminal — copy, paste, replace <code>YOUR_KEY</code>.
In code the key travels in the <code>X-API-Key</code> header rather than the URL:</p>
<pre><code>curl -H "X-API-Key: YOUR_KEY" \\
  "{E(base)}/matches?status=live"</code></pre>
<p>Your key is on <a href="{SITE}/account">{SITE}/account</a> behind
<strong>Show my key</strong>.</p>

<h2 id="base-url">Base URL</h2>
<pre class="urls"><code>{E(base)}</code></pre>

<h2 id="authentication">Authentication</h2>
<p>Three ways to present your key — all equivalent. Use the header in code; use
<code>?token=</code> when you just want to click a link or test from a browser or phone.
The <code>/health</code> endpoint needs no key.</p>
<pre><code>Authorization: Bearer twjp_...
X-API-Key: twjp_...
?token=twjp_...            in the URL — browser-friendly</code></pre>
<p class="meta">A key in a URL can end up in browser history, server logs and referrer
headers, so prefer a header for anything automated or shared. For trying the API out,
clicking a link is the fastest route and that trade-off is fine.</p>

<h2 id="plans">Plans</h2>
<p>Every plan includes everything in the plans below it. The table shows the
<strong>delta</strong> — exactly what each upgrade adds, and the request budget you get.</p>
<div class="scrollx" tabindex="0" role="region" aria-label="Plans and pricing">
<table><caption class="vh">Plans — what each tier adds over the one below, its rate limit and price</caption>
<thead><tr><th scope="col">Plan</th><th scope="col">Adds</th><th scope="col">Rate limit</th><th scope="col">Price</th></tr></thead><tbody>
<tr><th scope="row">FREE</th><td>The current state of the game: live &amp; upcoming matches, current scores, players, fixtures, your usage stats. No history, no market prices, no model fields, no WebSocket.</td><td>30/min &middot; 100/day</td><td>$0 — no card</td></tr>
<tr><th scope="row">BASIC</th><td>Historical data, in two continuous halves: the point-by-point tape (2023&rarr;now) — the completed-match listing (<code>/history/matches</code>, <code>status=completed</code>) and the full per-match tape with the model win-probability on the rows where the model ran (<code>/history/matches/{{matchId}}</code>) and the measured completeness rollup per tour &times; draw bucket (<code>/history/coverage</code>) — and the results archive (1968&ndash;2022): deep results (<code>/history/archive/matches</code>), archive player bios, career aggregates and head-to-head (<code>/h2h</code>).</td><td>60/min &middot; 1,000/day</td><td>$9.99/mo</td></tr>
<tr><th scope="row">PRO</th><td>Match events, market prices (<code>/markets</code>), the pre-built bulk history packages (<code>/history/packages</code>, JSONL/CSV), the rank-ordered rankings listing (<code>/rankings?system=</code>), and per-player records over our matches (<code>/players/{{playerId}}/stats</code>).</td><td>300/min &middot; 10,000/day</td><td>$29.99/mo</td></tr>
<tr><th scope="row">ULTRA</th><td>Model analysis, live <code>win_probability_p1</code> + <code>danger</code> on every score, in-play match statistics and their per-player sums (<code>serve_return</code> on <code>/players/{{playerId}}/stats</code>), live per-point events (<code>/matches/{{matchId}}/points</code> + the WebSocket <code>point</code> frames, where a point-level feed covers the match), per-player as-of ranking records, the as-of Elo tape (<code>/rankings?system=elo</code>), rally construction (shot-by-shot charted data), the WebSocket push feed, outbound webhooks.</td><td>600/min &middot; 500,000/day</td><td>$99.99/mo</td></tr>
</tbody></table></div>
<p class="scrollnote">The table above scrolls sideways.</p>
<p>Calling an endpoint above your plan returns <code>403 {{"error":"upgrade_required"}}</code> —
never a silent empty result. <a href="{SITE}/#pricing">See pricing</a>.</p>

<h3 id="history-plans">Historical Data API — standalone plans</h3>
<p>The <code>/history</code> endpoints are also sold on their own, without a live-API
subscription:</p>
<div class="scrollx" tabindex="0" role="region" aria-label="Historical Data API plans">
<table><caption class="vh">Historical Data API plans — what each adds</caption>
<thead><tr><th scope="col">Plan</th><th scope="col">Adds</th></tr></thead><tbody>
<tr><th scope="row">Starter</th><td>Single-match point-by-point tape reads via the API — the tape plus the model win-probability where computed — for all tours (ATP, WTA, Challenger, ITF), one match per request. No bulk downloads.</td></tr>
<tr><th scope="row">Pro</th><td>Everything in Starter, plus bulk monthly package downloads and higher rate limits.</td></tr>
<tr><th scope="row">Business</th><td>Everything in Pro, plus year-scale archive exports, top rate limits and priority support.</td></tr>
<tr><th scope="row">One-off passes</th><td>1-month and 1-year access passes, no subscription.</td></tr>
</tbody></table></div>
<p class="scrollnote">The table above scrolls sideways.</p>
<p>Plans and prices: <a href="{SITE}/historical-tennis-data-api">{SITE}/historical-tennis-data-api</a>.</p>

<h3 id="alerts-plans">Break-point Alerts — hosted alerts, no code</h3>
<p>A hosted companion product that pushes break-point alerts to your channels
(the same signal the ULTRA WebSocket <code>break_point</code> frame carries, without
running a client). <strong>Free</strong>: high-swing break points only (probability swing
&ge; 0.15), one delivery channel. <strong>Pro ($9.99/mo)</strong>: every break point — no
swing floor — to unlimited channels: Telegram, Discord, email, SMS, WhatsApp.
Details: <a href="{SITE}">livetennisapi.com</a>.</p>

<h2 id="clients">Official client libraries</h2>
<div class="scrollx" tabindex="0" role="region" aria-label="Official client libraries">
<table class="linkrow"><caption class="vh">Official client libraries — install command and source repository</caption>
<thead><tr><th scope="col">Language</th><th scope="col">Install</th><th scope="col">Source</th></tr></thead><tbody>
<tr><th scope="row">Python</th><td><code>pip install livetennisapi</code></td><td><a href="https://github.com/livetennisapi/livetennisapi-python">livetennisapi-python</a></td></tr>
<tr><th scope="row">JavaScript / TypeScript</th><td><code>npm install livetennisapi</code></td><td><a href="https://github.com/livetennisapi/livetennisapi-js">livetennisapi-js</a></td></tr>
<tr><th scope="row">MCP server (LLM agents)</th><td>hosted at <code>https://mcp.livetennisapi.com/mcp</code>, or <code>npx livetennisapi-mcp</code></td><td><a href="https://github.com/livetennisapi/livetennisapi-mcp">livetennisapi-mcp</a></td></tr>
</tbody></table></div>

<h2 id="mcp">MCP server</h2>
<p>Two ways to put this API behind an LLM agent. Both expose the same 25 read-only tools, and
both authorise every tool call on your own key, so a tool reaches what your plan reaches.</p>
<p><strong>Hosted.</strong> POST to <code>https://mcp.livetennisapi.com/mcp</code>
(Streamable HTTP, POST only) and send your key as
<code>Authorization: Bearer twjp_...</code> or <code>X-API-Key: twjp_...</code>. Nothing to
install and nothing to keep running. <code>GET https://mcp.livetennisapi.com/health</code>
reports the running version.</p>
<p><strong>Self-run.</strong> <code>npx livetennisapi-mcp</code> with
<code>LIVETENNISAPI_KEY</code> in the environment. Listed in the official MCP Registry as
<code>io.github.livetennisapi/livetennisapi-mcp</code>, source at
<a href="https://github.com/livetennisapi/livetennisapi-mcp">livetennisapi-mcp</a>.</p>
<p>Without a key only <code>check_api_status</code> answers, and it says where to get a free
one. The hosted endpoint allows 300 requests a minute on a key and 60 without one. Your
plan's own rate limit applies underneath that.</p>
<p>The 25 tools: <code>get_live_matches</code>, <code>get_upcoming_matches</code>,
<code>get_match</code>, <code>get_match_score</code>, <code>get_fixtures</code>,
<code>get_recent_results</code>, <code>search_players</code>, <code>get_player</code>,
<code>search_tournaments</code>, <code>get_tournament</code>, <code>get_h2h</code>,
<code>get_rankings</code>, <code>get_player_rankings</code>, <code>get_match_events</code>,
<code>get_match_odds</code>, <code>get_match_analysis</code>,
<code>get_match_statistics</code>, <code>search_archive_matches</code>,
<code>get_archive_match</code>, <code>search_archive_players</code>,
<code>get_archive_career</code>, <code>get_charting_player</code>,
<code>get_charting_match</code>, <code>player_stats</code>, <code>check_api_status</code>.</p>

<h2 id="conventions">Conventions</h2>
<ul>
<li>Timestamps are UTC ISO 8601 with a <code>Z</code> suffix.</li>
<li>List endpoints return <code>{{data, meta}}</code>; single resources return the object directly.</li>
<li><code>limit</code> defaults to 50; the API rejects anything above 200. Paginate with <code>offset</code>.</li>
<li><strong>Ignore unknown fields.</strong> Additive changes ship within <code>v1</code>, so a client that
rejects unrecognised fields will break. Every official SDK parses permissively.</li>
<li><strong>Score shape:</strong> <code>sets</code> is <code>[sets_p1, sets_p2]</code>.
<code>games</code> is <code>[games_p1, games_p2]</code> where each side is a <em>per-set</em> list —
so <code>[[6,3,2],[4,6,1]]</code> reads 6-4, 3-6, 2-1. It is player-major, not set-major.</li>
</ul>

<h2 id="endpoints">Endpoints</h2>
<ul class="toc">
{chr(10).join(toc)}
</ul>

{chr(10).join(ops)}

<h2 id="websocket">WebSocket feed (ULTRA)</h2>
<p>A native WebSocket live feed is available at <code>{E(base)}/ws</code>. Subscribe with
<code>{{"topics":["live-scores"]}}</code> or
<code>{{"topics":["match:&lt;id&gt;"]}}</code>. The server acknowledges with a
<code>subscribed</code> frame, then pushes <code>score</code> frames on every change plus a
<code>ping</code> heartbeat roughly every 15 seconds.</p>
<p>Opt into extra signals by adding a <code>signals</code> array to the subscribe frame —
<code>{{"topics":["live-scores"],"signals":["break_point"]}}</code> — to also receive a
<code>break_point</code> frame the instant a break point arises and a
<code>break_point_result</code> frame when it resolves. Their shapes are the
<code>BreakPoint</code> and <code>BreakPointResult</code> schemas below. Without
<code>signals</code> the feed pushes <code>score</code> frames only, exactly as before.</p>
<p><code>signals</code> may also name <code>points</code> — the live per-point event
stream: one <code>point</code> frame per persisted point of your subscribed matches
(shape <code>PointFrame</code> below), ordered per match by <code>seq</code>. The signal
is config-gated and ships off by default; the <code>subscribed</code> ack echoes the
signals actually active, so <code>points</code> missing from the ack means no point
frames will flow. Frames arrive only for matches with
<code>pbp_coverage: "point"</code> — a <code>game</code>-coverage match sends none,
honestly. Point frames are events, not states, and there is no WS replay: a missed
one does not self-correct on the next frame — on reconnect, or to join mid-match,
catch up via <code>GET /matches/{{matchId}}/points?after_seq=</code> and dedup by
<code>seq</code>. The push feed carries the same frames on their own channel family
(<code>point:match:{{matchId}}</code> and <code>point:slate</code>), deliberately separate
from the score channels.</p>

<h2 id="faq">FAQ — plans and data depth</h2>

<h3 id="faq-how-much">How much data can I access on each plan?</h3>
<p><strong>FREE</strong> sees the current state of the game only — live and upcoming matches,
scores, players and fixtures — at 100 requests/day. <strong>BASIC</strong> adds every
completed match and its full point-by-point tape (with the model
win-probability where computed), one match per request, at 1,000/day.
<strong>PRO</strong> adds whole months of history in a single bulk file (JSONL or CSV),
plus match events and market prices, at 10,000/day. <strong>ULTRA</strong> adds model
analysis, the live model fields and the WebSocket push feed, at 500,000/day.
Coverage is identical on every plan: all tours, ATP through ITF — the plans
differ in which data products and volumes they unlock, never in which
tournaments you see.</p>

<h3 id="faq-how-far-back">How far back does history go?</h3>
<p><strong>1968.</strong> History runs in two continuous, non-overlapping halves. The
<strong>point-by-point tape (2023&rarr;now)</strong>: <code>/history/matches</code> pages every completed
match from January 2023 on, all tours, newest first — filter a window with
<code>from</code>/<code>to</code> — with the per-match point-by-point tape at
<code>/history/matches/{{matchId}}</code>. The <strong>results archive (1968&ndash;2022)</strong>:
<code>/history/archive/matches</code> serves winner/loser-shaped RESULTS — ATP and WTA,
main draws, qualifying and the ITF/futures tiers, 1968 through 2022 — with
final score, seeds, ranks at the time, and per-match serve statistics where
the era recorded them (from 1991). The archive ends exactly where the tape
begins, so no match is ever served from two datasets. Archive results played
<strong>2013&ndash;2022</strong> additionally carry a reconstructed point-by-point tape
(next question). Bulk: tape packages are
built per calendar month, archive packages per year
(<code>?kind=archive</code>), the reconstructed archive tape per year
(<code>?kind=archive_tape</code>, 2013&ndash;2022);
<code>GET /history/packages</code> lists exactly which periods
exist and is always the authoritative answer. Year-scale exports are part of
the Historical Data API Business plan.</p>

<h3 id="faq-pre-2023-points">Is there point-by-point data before 2023?</h3>
<p><strong>For 2013&ndash;2022, yes — reconstructed, not recorded.</strong>
<code>GET /history/archive/matches/{{archiveId}}/tape</code> serves the score sequence
behind a 2013&ndash;2022 archive result: reconstructed point sequences, no capture
timestamps. <strong>97,901 matches and 14,340,663 rows</strong>. The floor is hard. The
archive holds a further <strong>977,903 results from 1968&ndash;2012 and not one of
them has a tape</strong>. We hold no point sequence for those years, and we do not
manufacture one.</p>
<p><strong>Nobody watched those matches, and the data says so.</strong>
<code>timestamp</code>, <code>win_probability_p1</code> and <code>danger</code> are
null on <em>every</em> row and cannot be filled in later — the production table has no
timestamp column at all, and the promotion script refuses to run if one ever
appears. This is structural, not a convention. Do not time
anything with this tape: it is true about the score sequence and silent about the
clock. That is the opposite of the 2023&rarr;now tape, which is our own recording —
there, the rows we actually watched carry a real clock and most of them a model
probability. <code>meta</code> states the rest per match:
<code>coverage</code> (<code>reconstructed</code> | <code>reconstructed_partial</code>),
<code>granularity</code> (<code>point</code> on 99.4% of the corpus; 556 matches resolve
only to one row per game, 555 of them in 2013), <code>point_source</code> and
<code>rows</code>. <code>reconstructed_partial</code> (3,594 matches) has two causes and
does not say which: 3,038 are matches that genuinely stopped early (3,027
retirements, 11 defaults) and the other 556 carry the label only because their tape
is per-game — read <code>granularity</code> and the match's own score, not the
label.</p>
<p><strong>How much of the era it covers, thin spots included:</strong> 19.3% of all
archive matches played 2013&ndash;2022 and 44.9% of tour-level play. Main-draw tour
buckets are close to complete — ATP Masters 98.7%, ATP slam 98.0%, WTA slam 97.4%,
WTA Premier Mandatory 97.9%, ATP 250&ndash;500 95.4%, WTA Premier 94.1%. Below that
it thins fast: ATP Challenger main draws 55.3%, Challenger qualifying 33.6%, slam
<em>qualifying</em> only 16.0% (ATP) and 18.1% (WTA), and ITF and futures effectively
nothing — 25 of 116,575 ATP futures matches, 68 of 19,162 ITF M15, 48 of 9,380 ITF
M25. If your work is ITF, this is the wrong dataset and we would rather you knew
now. 31% of the corpus is qualifying-draw play, which is the part you are least
likely to hold already.</p>
<p><strong>Each tape is proved to belong to its match before it is published.</strong>
A five-clause identity proof — edition, names, round, an exact match of the derived
set spine against the published final score, and the date window — then a step-by-step
walk against 23 interior invariants. A tape that cannot prove its binding is refused
rather than published against a guess, which is why a missing tape and an unproven one
both answer 404.</p>
<p><strong>Who can read it:</strong> core ULTRA, <em>or any active History plan
including Starter</em> (which opens it on a FREE core key). The per-year bulk files
(<code>/history/packages?kind=archive_tape</code>, 2013&ndash;2022, JSONL and CSV, all
ready) are a separate gate: core ULTRA, a History Pro/Business subscription, or an
active one-off package window. <strong>Core PRO carries neither</strong> — it reads the
archive result and is refused the tape.</p>

<h3 id="faq-whats-in-tape">What's in the point-by-point tape?</h3>
<p>One row per recorded point state, chronological: <code>sets</code>, per-set <code>games</code>,
in-game <code>points</code>, the <code>server</code>, the tiebreak flag, and the model's
<code>win_probability_p1</code> and <code>danger</code> on the rows where the model ran (null
elsewhere — check <code>meta.model_rows</code>); rows we watched live carry a real
timestamp, reconstructed rows a null one.
<code>GET /history/matches/{{matchId}}</code> returns it per match (shape
<code>HistoryTape</code>: match metadata + tape + the model profiles produced during the
match). Add <code>?points=complete</code> to opt into a whole-match reconstruction
where one exists — the response's <code>meta.points</code> block reports the measured
point-completeness of exactly the sequence you were served, per match, never as
a blanket claim. Filter the listing by that measured verdict with
<code>?points_complete=true</code> on <code>/history/matches</code>. The monthly bulk
packages' base files carry each match's default read — the same tape the API
serves — and a month may also list the complete-basis addendum files
(<code>tennis_history_points_complete_&lt;period&gt;.jsonl.gz</code>/<code>.csv.gz</code>): the same
tape <code>?points=complete</code> serves, for exactly the matches whose complete point
sequence exists only as the on-disk reconstruction. Existing base files are
never rewritten by the addendum; their <code>sha256</code> values do not move.
Measured completeness also differs sharply by draw on some circuits — as of
2026-08-18, 51.1% of ITF singles matches are point-complete on the best basis
against 3.5% of ITF doubles — which is exactly the split the <code>?draw=</code> filter
and <code>GET /history/coverage</code> (the per-bucket rollup, rebuilt nightly, dated by
its own <code>as_of</code>) exist to expose. Do not extrapolate a completeness rate
across a <code>?tour=</code> group.</p>

<h2 id="schemas">Schemas</h2>
{schema_html}

</main>

<footer>
<hr>
<p class="meta">Generated from <a href="./openapi.yaml">openapi.yaml</a> by
<a href="https://github.com/livetennisapi/openapi">livetennisapi/openapi</a>.</p>
<nav class="footnav" aria-label="Elsewhere">
<a href="https://github.com/livetennisapi/openapi/issues">Report a spec mismatch</a>
<a href="https://affiliates.livetennisapi.com/program">Affiliate programme — 51% lifetime</a>
</nav>
<p class="meta">Writing about tennis, or building a tool on this API? The affiliate
programme pays 51% recurring for the lifetime of every subscription referred,
10% off for them, free to join.</p>
{CREDIT}
</footer>

</div>
{BEACON}{CLARITY}</body>
</html>
"""


def build_llms_txt(spec: dict[str, Any]) -> str:
    """A spec digest for answer engines, mirroring the main site's llms.txt."""
    base = spec["servers"][0]["url"]
    lines = [
        "# Live Tennis API — API Reference",
        "",
        "> Complete endpoint reference for the Live Tennis API. Real-time tennis scores,",
        "> players, rankings, match-winner market prices and model win-probability for ATP,",
        "> WTA, Challenger and ITF, over REST and WebSocket — plus the point-by-point tape",
        "> (2023→now), the results archive (1968–2022) of deep historical results, and the",
        "> reconstructed 2013–2022 archive tape (97,901 matches, 14,340,663 rows).",
        "",
        f"Base URL: {base}",
        f"Full text reference: {DOCS_URL}/reference.html",
        f"Changelog (dated, versioned): {DOCS_URL}/changelog.html",
        f"OpenAPI spec: {DOCS_URL}/openapi.yaml",
        f"OpenAPI spec (JSON): {DOCS_URL}/openapi.json",
        f"Website: {SITE}",
        # Plan 3 V12 asks every llms.txt to link pricing. This one linked the affiliate
        # signup and the whole docs tree but never the pricing page, so a machine reading
        # the DOCS host to answer "what does the Live Tennis API cost" had no pointer —
        # while the docs HTML pages themselves have linked /pricing since WS11.2. The gap
        # was between the human surface and the machine one, which is the surface that
        # matters most here.
        f"Plans and pricing: {SITE}/pricing",
        "",
        "## Pages by topic",
        "Each answers one question and carries the full parameter and response detail for its",
        "endpoints, generated from the same spec as the reference:",
        *[f"- {t['question']} {DOCS_URL}/{t['slug']}.html" for t in TOPICS],
        "",
        "## Guides",
        *[f"- {t['question']} {DOCS_URL}/{t['slug']}.html" for t in GUIDES],
        "",
        "## Quickstart (no code required)",
        f"Open this in a browser — no install, no headers: {base}/matches?status=live&token=YOUR_KEY",
        "Reading a score: every array is PLAYER-MAJOR — first list is player 1, second is player 2.",
        '  "sets": [1,0] = p1 leads one set to nil.',
        '  "games": [[6,3],[4,4]] = 6-4 in the first set, 3-4 in the second.',
        '  "points": ["0","0"] = the game in progress. "server": 1 = player 1 serving.',
        "",
        "## Authentication",
        "Send the API key as `Authorization: Bearer <key>`, `X-API-Key: <key>`, or `?token=<key>`",
        "in the query string. The query form is browser-friendly (clickable links, phones); prefer",
        "a header for anything automated, since URLs leak into logs, history and referrers.",
        "The /health endpoint requires no key.",
        "",
        "## Errors and retries",
        f"Every error is JSON with a stable `error` code. Full table: {DOCS_URL}/errors-and-rate-limits.html",
        *[f"- {status}: " + ", ".join(sorted({c for s, codes, _, _ in ERROR_CODES if s == status for c in codes}))
          for status in sorted({s for s, _, _, _ in ERROR_CODES})],
        "Retry a per-minute 429 (rate_limited, no scope) and any 5xx, waiting Retry-After when it",
        "is sent. Never retry a daily 429 (scope: \"day\", wait until resets_at) or abuse_throttled",
        "(wait until retry_at_epoch). The official Python and JS clients do exactly this, 2 retries",
        "by default. 400, 401, 403, 404, 409 and 410 are fixed on the client side, not retried.",
        "",
        "## Plans",
        "Every plan includes the plans below it. The concrete deltas:",
        "- FREE ($0, no card) — live & upcoming matches, current scores, players, fixtures,",
        "  usage stats. 30 req/min, 100 req/day. No history, no market prices, no model",
        "  fields, no WebSocket.",
        "- BASIC ($9.99/mo) — adds history, in two continuous halves: the point-by-point",
        "  tape (2023→now) — the completed-match listing, the per-match tape with the",
        "  model win-probability where computed, and the measured completeness rollup",
        "  per tour × draw bucket (/history/coverage) — and the results archive",
        "  (1968–2022): deep results, archive player bios, career aggregates and",
        "  head-to-head (/h2h). 60 req/min, 1,000 req/day.",
        "- PRO ($29.99/mo) — adds match events, market prices, bulk history packages",
        "  (JSONL/CSV), the rank-ordered rankings listing, and per-player records over our",
        "  matches (/players/{playerId}/stats). 300 req/min, 10,000 req/day.",
        "- ULTRA ($99.99/mo) — adds model analysis, live win_probability_p1 + danger,",
        "  in-play match statistics, live per-point events (/matches/{matchId}/points +",
        "  the WebSocket point frames, where a point-level feed covers the match),",
        "  serve_return on /players/{playerId}/stats (per-match statistics summed over the",
        "  window), per-player as-of rankings, the as-of Elo tape (system=elo), rally construction",
        "  (shot-by-shot charted data), the reconstructed 2013–2022 archive tape",
        "  (/history/archive/matches/{archiveId}/tape — also opened by ANY active History",
        "  plan, Starter included), the WebSocket push feed and webhooks.",
        "  600 req/min, 500,000 req/day.",
        "",
        "Coverage is identical on every plan (all tours, ATP through ITF); plans differ in",
        "which data products and volumes they unlock. Calling above your plan returns",
        "403 {\"error\":\"upgrade_required\"}.",
        "",
        "## Historical Data API (standalone plans for the /history endpoints)",
        "- Starter — single-match point-by-point tape reads (tape + model win-probability",
        "  where computed), all tours, one match per request, INCLUDING the reconstructed",
        "  2013–2022 archive tape. No bulk downloads.",
        "- Pro — everything in Starter + bulk monthly package downloads (and the per-year",
        "  archive_tape files) + higher rate limits.",
        "- Business — everything in Pro + year-scale archive exports + top rate limits +",
        "  priority support.",
        "- One-off passes — 1-month and 1-year access, no subscription.",
        f"Prices: {SITE}/historical-tennis-data-api",
        "",
        "## Break-point Alerts (hosted alerts, no code)",
        "- Free — high-swing break points only (probability swing >= 0.15), one delivery channel.",
        "- Pro ($9.99/mo) — every break point (no swing floor), unlimited channels:",
        "  Telegram, Discord, email, SMS, WhatsApp.",
        "",
        "## Endpoints",
    ]
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            lines.append(f"- {method.upper()} {path} — {op.get('summary','')}")
    lines += [
        "",
        "## FAQ",
        "How much data can I access on each plan? FREE = the current state only, 100",
        "req/day. BASIC = + every completed match and its full point-by-point tape, one",
        "match per request, 1,000/day. PRO = + whole months of history in one bulk file,",
        "plus events and market prices, 10,000/day. ULTRA = + model analysis and live",
        "push, 500,000/day.",
        "How far back does history go? 1968, in two continuous halves. The point-by-point",
        "tape (2023→now): /history/matches pages every completed match from January 2023",
        "on (filter with from/to). The results archive (1968–2022): /history/archive/matches",
        "serves winner/loser-shaped results — ATP and WTA, main draws, qualifying and the",
        "ITF/futures tiers, 1968 through 2022 — with seeds, ranks at the time, and serve",
        "stats where the era recorded them (from 1991). The archive ends where the tape",
        "begins. GET /history/packages lists exactly which bulk periods exist (monthly for",
        "tape, yearly for ?kind=archive and ?kind=archive_tape) and is always the",
        "authoritative answer.",
        "Is there point-by-point data before 2023? For 2013–2022 yes, RECONSTRUCTED, not",
        "recorded: GET /history/archive/matches/{archiveId}/tape serves the score sequence",
        "behind a 2013–2022 archive result as reconstructed point sequences, no capture",
        "timestamps. 97,901 matches and 14,340,663 rows. The floor is hard: 977,903 archive",
        "results from 1968–2012 have NO tape and never will, because we hold no point",
        "sequence for those years and we do not manufacture one. Nobody watched those matches, so",
        "timestamp, win_probability_p1 and danger are null on EVERY row and cannot be filled",
        "in later — the production table has no timestamp column at all, and the promotion",
        "script refuses to run if one ever appears. Do not time",
        "anything with this tape. The 2023→now tape is the opposite: it is our own",
        "recording, and the rows we actually watched carry a real clock and most of them a",
        "model probability. meta per match: coverage (reconstructed | reconstructed_partial),",
        "granularity (point on 99.4% of the corpus; 556 matches are one row per game, 555 of",
        "them in 2013), point_source, rows. reconstructed_partial (3,594 matches) has two",
        "causes and does not say which — 3,038 matches that genuinely stopped early (3,027",
        "retirements, 11 defaults) and 556 that carry the label only for being per-game.",
        "Coverage of the era, thin spots included: 19.3% of archive matches played 2013–2022",
        "and 44.9% of tour-level play; ATP slam main 98.0%, WTA slam main 97.4%, ATP Masters",
        "98.7%, ATP 250–500 95.4%, WTA Premier 94.1%, WTA Premier Mandatory 97.9%, Challenger",
        "main 55.3%, Challenger qualifying 33.6%; slam QUALIFYING only 16.0% (ATP) / 18.1%",
        "(WTA); ITF and futures effectively zero (25 of 116,575 ATP futures, 68 of 19,162",
        "M15, 48 of 9,380 M25). 31% of the corpus is qualifying-draw play. It is not a",
        "complete record of the era and is not sold as one. Every tape is bound to its match",
        "by a five-clause identity proof and a 23-invariant interior audit; one that cannot",
        "prove its binding is refused rather than published against a guess. Tier: core ULTRA",
        "or ANY active History plan including Starter; the per-year bulk files",
        "(?kind=archive_tape, 2013–2022, JSONL + CSV, all ready) need core ULTRA, a History",
        "Pro/Business subscription, or an active one-off package window. Core PRO carries",
        "NEITHER.",
        "What's in the point-by-point tape? One row per recorded point state:",
        "sets, per-set games, in-game points, server, tiebreak flag, and the model's",
        "win_probability_p1 + danger on the rows where the model ran (null elsewhere —",
        "check meta.model_rows). ?points=complete opts into a whole-match reconstruction",
        "where one exists; the response's meta.points block reports the measured",
        "point-completeness of exactly the sequence served — per match, never a blanket",
        "claim. ?points_complete=true filters /history/matches by that measured verdict,",
        "and ?draw=singles|doubles slices four listings (/matches, /history/matches,",
        "/tournaments, /fixtures) by the three-valued draw field — a null-draw row",
        "matches neither value. Measured completeness differs sharply by draw on some",
        "circuits (as of 2026-08-18: 51.1% of ITF singles point-complete on the best",
        "basis vs 3.5% of ITF doubles) — read GET /history/coverage, the per-bucket",
        "rollup rebuilt nightly and dated by its own as_of, before choosing what to",
        "backtest.",
        "",
        "## Official client libraries",
        "- Python: `pip install livetennisapi` — https://github.com/livetennisapi/livetennisapi-python",
        "- JavaScript/TypeScript: `npm install livetennisapi` — https://github.com/livetennisapi/livetennisapi-js",
        "- MCP server for LLM agents, hosted: POST https://mcp.livetennisapi.com/mcp (Streamable HTTP;",
        "  send your key as `Authorization: Bearer twjp_...` or `X-API-Key: twjp_...`). Same 25",
        "  read-only tools on every plan, free keys included, each tool reaching what that plan",
        "  reaches. Nothing to install.",
        f"- MCP server, self-run: `npx livetennisapi-mcp`, package {NPM_MCP_URL}, source https://github.com/livetennisapi/livetennisapi-mcp",
        f"- Vercel AI SDK tools: `npm install livetennisapi-ai`, package {AI_SDK_NPM}, source https://github.com/livetennisapi/livetennisapi-ai",
        f"  (guide: {DOCS_URL}/ai-sdk.html). The same 25 tools as the MCP server, as AI SDK tools.",
        "  Reads the key from LIVETENNISAPI_KEY. Needs `ai` v7, which needs Node 22 or later.",
        f"- CSV, JSON Lines and Parquet export: `pip install livetennisapi-export`, package {EXPORT_PYPI},",
        f"  source {EXPORT_REPO} (guide: {DOCS_URL}/export-formats.html). Six datasets: matches,",
        "  fixtures, players, player, rankings and tournaments. Reads the key from LIVETENNISAPI_KEY.",
        *[f"- {c['name']}: `{c['install']}`, package {c['registry_url']}, source {c['repo']}"
          for c in CLIENTS if c["key"] in CLIENTS_LLMS_EXTRA],
        f"- Every library with its latest version, minimum runtime and endpoint coverage: {DOCS_URL}/client-libraries.html",
        "",
        "## Affiliate programme",
        "- https://affiliates.livetennisapi.com/program — 51% recurring commission for the lifetime",
        "  of every subscription referred, 10% discount for the referred customer, 30-day attribution.",
        "- Free to join, open to developers, creators and tennis writers:"
        " https://affiliates.livetennisapi.com/signup",
        "",
        "## Notes",
        "- Timestamps are UTC ISO 8601 with a Z suffix.",
        "- List endpoints return {data, meta}; single resources return the object directly.",
        "- limit defaults to 50, maximum 200; paginate with offset.",
        "- Additive changes ship within v1: clients must ignore unknown fields.",
        "- Score `games` is player-major: [[6,3,2],[4,6,1]] reads 6-4, 3-6, 2-1.",
        "",
    ]
    return "\n".join(lines)



# --------------------------------------------------------------------------- changelog --------
CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
_ENTRY_RX = re.compile(r"^## \[(?P<ver>[^\]]+)\] - (?P<date>\d{4}-\d{2}-\d{2})\s*$")


def changelog_entries(text: str) -> list[dict]:
    """[{version, date, body_md}] newest first, from the Keep-a-Changelog headings."""
    out: list[dict] = []
    for line in text.splitlines():
        m = _ENTRY_RX.match(line)
        if m:
            out.append({"version": m["ver"], "date": m["date"], "lines": []})
        elif out:
            out[-1]["lines"].append(line)
    for e in out:
        e["body_md"] = "\n".join(e.pop("lines")).strip()
    return out


_BOLD_RX = re.compile(r"\*\*(.+?)\*\*")


def _inline(text: str) -> str:
    return _BOLD_RX.sub(r"<strong>\1</strong>", md_inline(text))


def _md_block(md: str) -> str:
    """The small Markdown subset the changelog uses: ### headings, - bullets, **bold**, paragraphs.

    A `###` inside an entry renders as <h3>, one level below the entry's own <h2>. It used to
    render as <h4> under an <h3> entry heading; promoting the entry to <h2> without promoting its
    body would have left h2 -> h4, which is the same skipped level in a new place.
    """
    html_parts: list[str] = []
    in_list = False
    para: list[str] = []

    def flush_para() -> None:
        if para:
            html_parts.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("### "):
            flush_para()
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h3>{E(line[4:])}</h3>")
        elif line.startswith("- "):
            flush_para()
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"<li>{_inline(line[2:])}</li>")
        elif line and in_list and html_parts and html_parts[-1].endswith("</li>"):
            # A continuation line belongs to the open item, indented or not. Markdown's lazy
            # continuation reads it that way, and treating an unindented one as a paragraph
            # put a <p> straight inside the <ul> (1.13.60's entry did exactly that).
            html_parts[-1] = html_parts[-1][:-5] + " " + _inline(line.strip()) + "</li>"
        elif not line:
            flush_para()
            if in_list:
                html_parts.append("</ul>")
                in_list = False
        else:
            para.append(line.strip())
    flush_para()
    if in_list:
        html_parts.append("</ul>")
    return "\n".join(html_parts)


def build_changelog(spec: dict[str, Any], reference_html: str) -> tuple[str, str]:
    """(html, latest_date). Same head shape and stylesheet as the reference so it reads as one
    site; each entry is a dated <article> so an engine can quote 'as of' from the page itself.
    The sitemap's lastmod for this page is the newest entry's date — a date the file proves."""
    entries = changelog_entries(CHANGELOG.read_text(encoding="utf-8"))
    latest = entries[0]["date"] if entries else ""
    style_html = reference_base_style(reference_html)
    articles = "\n".join(
        f'<article id="v{E(e["version"])}"><h2>{E(e["version"])} <time datetime="{e["date"]}">{e["date"]}</time></h2>\n{_md_block(e["body_md"])}</article>'
        for e in entries
    )
    info = spec["info"]
    desc = ("Every change to the Live Tennis API specification, dated and versioned: additive "
            f"within v1, newest first. Current version {info['version']}, last change {latest}.")
    ld_json = tech_article_ld(f"{info['title']} — Changelog", desc, f"{DOCS_URL}/changelog.html",
                              dateModified=latest)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(info['title'])} — Changelog</title>
<meta name="description" content="{E(desc)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{DOCS_URL}/changelog.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{E(info['title'])} — Changelog">
<meta property="og:url" content="{DOCS_URL}/changelog.html">
<meta property="og:image" content="{DOCS_URL}/banner.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="favicon.ico" sizes="any">
<script type="application/ld+json">
{ld_json}
</script>
{FONT_PRELOADS}{INLINE_STYLES}
{style_html}{DESIGN_STYLES}
</head>
<body class="docs-page docs-changelog">
<a class="skip-link" href="#main">Skip to content</a>
{site_navigation('changelog')}
<main class="wrap" id="main">
<header>
<p class="eyebrow">Live Tennis API · docs</p>
<h1>Changelog</h1>
<p>Every change to the specification, dated and versioned. The API surface is <code>v1</code>; changes within it are additive only. Current version <strong>{E(info['version'])}</strong>, last change <time datetime="{latest}">{latest}</time>. Also as <a href="{DOCS_URL}/reference.html">the full reference</a>, <a href="{DOCS_URL}/openapi.yaml">OpenAPI YAML</a> / <a href="{DOCS_URL}/openapi.json">JSON</a>, and <a href="{SITE}/facts.json">the dated facts file</a>.</p>
</header>
{articles}
</main>
{BEACON}{CLARITY}</body>
</html>
"""
    return page, latest

# ---------------------------------------------------------------------------
# Per-topic pages
#
# WHY. The docs sitemap listed two URLs, and the whole 40-operation surface lived on one
# 36,000-word page. An answer engine asked "which tennis API returns point-by-point data"
# has to find that page, rank the whole of it for a question about one eighth of it, and
# quote from the middle. The 2026-09-14 AEO benchmark measured the cost: the discovery
# group cited us in 70% of runs against 100% for questions that name us, and the ONE
# question never answered with us in 244 runs — "which tennis APIs publish measured latency
# and uptime numbers" — is a question about a single topic.
#
# So: one page per topic, generated from the same spec, each answering its own question in
# its first paragraph. Nothing is hand-written that the spec already states; if the spec
# changes, these change with it.
#
# The matchers are exhaustive and exclusive BY ASSERTION (see build_topic_pages): a new
# path that matches none of them, or more than one, fails the build. A new endpoint must
# not be able to silently vanish from the documentation site.
# ---------------------------------------------------------------------------

TOPICS: list[dict[str, Any]] = [
    {
        "slug": "live-scores",
        "title": "Live tennis scores API",
        "question": "How do you read live tennis scores from the API?",
        "lede": (
            "Poll <code>GET /matches?status=live</code> for the slate, then "
            "<code>GET /matches/{matchId}/score</code> for the lowest-latency read of one match. "
            "Both are on the FREE plan. Scores carry sets, games, points and the server; "
            "<code>/events</code> and <code>/points</code> give the same match as a stream of "
            "changes rather than a snapshot, so a client can catch up without re-reading state."
        ),
        "paths": lambda p: (
            p in ("/matches", "/events", "/fixtures")
            or (p.startswith("/matches/{matchId}") and not p.endswith(("/prices", "/rally")))
        ),
    },
    {
        "slug": "players-and-tournaments",
        "title": "Tennis players, tournaments and rankings API",
        "head_title": "Players, tournaments and rankings API — Live Tennis API",
        "question": "How do you look up a player, a tournament or a ranking?",
        "lede": (
            "<code>GET /players</code> searches by name and <code>GET /players/{playerId}</code> "
            "returns one player's bio, current ranking and cached statistics — both FREE. "
            "<code>GET /players/{playerId}/stats</code> (PRO) is the player's win/loss record over "
            "our completed matches, split by surface, level and season, with ULTRA adding summed "
            "serve and return statistics. "
            "<code>GET /tournaments</code> is the catalogue that <code>Match.tournament_id</code> "
            "joins against, so a match can be resolved to its event without a second lookup. "
            "<code>GET /rankings</code> serves rank-ordered listings on PRO. The per-player as-of "
            "records, including the Elo tape, are ULTRA."
        ),
        "paths": lambda p: p.startswith(("/players", "/tournaments", "/rankings")),
    },
    {
        "slug": "tennis-odds",
        "title": "Tennis odds API — markets and price ticks",
        "question": "How do you read tennis match-winner odds and their price history?",
        "lede": (
            "<code>GET /markets</code> returns the match-winner market for a match and "
            "<code>GET /markets/{matchId}/prices</code> the recent price ticks per side, newest "
            "first; <code>GET /matches/{matchId}/prices</code> is the same ticks addressed by "
            "match id. All three are PRO. Every tick carries its own timestamp, so a series can "
            "be reconstructed rather than inferred from poll times."
        ),
        "paths": lambda p: p.startswith("/markets") or p == "/matches/{matchId}/prices",
    },
    {
        "slug": "point-by-point-history",
        "title": "Point-by-point tennis data API",
        "question": "Which endpoints return point-by-point tennis data, and how complete is it?",
        "lede": (
            "<code>GET /history/matches/{matchId}</code> returns the tape for one completed match: "
            "the ordered score states we hold for it. The model's win probability sits on the rows "
            "that were observed live, and coverage is declared per match. "
            "<code>GET /history/matches</code> lists completed matches with their tape coverage, and "
            "<code>GET /history/coverage</code> is the measured completeness rollup per tour and draw "
            "bucket — a number we publish rather than estimate, with its own <code>as_of</code>. "
            "<code>GET /history/packages</code> serves the same data as pre-built monthly bulk files."
        ),
        "paths": lambda p: (
            p.startswith("/history/") and not p.startswith("/history/archive")
            and not p.endswith("/rally")
        ),
    },
    {
        "slug": "historical-results-archive",
        "title": "Historical tennis results API — 1968 onward",
        "head_title": "Historical tennis results API from 1968 — Live Tennis API",
        "question": "How far back does the historical tennis data go, and what is in it?",
        "lede": (
            "The results archive covers 1968 to 2022: <code>GET /history/archive/matches</code> for "
            "results, <code>/archive/players</code> for bios, <code>/archive/career</code> for career "
            "aggregates and <code>GET /h2h</code> for head-to-head across both the archive and our own "
            "completed matches. All BASIC. Matches from 2013 onward additionally carry a reconstructed "
            "point-by-point tape at <code>/archive/matches/{archiveId}/tape</code> (ULTRA)."
        ),
        "paths": lambda p: p.startswith("/history/archive") or p == "/h2h",
    },
    {
        "slug": "shot-level-rally-data",
        "title": "Shot-by-shot tennis rally and charting API",
        "question": "Is there tennis data below the point — shot by shot?",
        "lede": (
            "Yes, for charted matches. <code>GET /rally/matches</code> lists them and "
            "<code>/rally/matches/{rallyMatchId}</code> returns the rally construction; "
            "<code>GET /history/matches/{matchId}/rally</code> reaches the same data by our own match id "
            "so a live match and its charting share one identifier. <code>GET /charting/players</code> "
            "aggregates a player's career at shot level and <code>/charting/matches/{chartingMatchId}</code> "
            "returns every stat family for both players in one charted match. All ULTRA."
        ),
        "paths": lambda p: p.startswith(("/rally", "/charting")) or p.endswith("/rally"),
    },
    {
        "slug": "broadcast-graphics",
        "title": "Tennis scores for on-air graphics",
        "question": "How do you put live tennis scores into a broadcast graphics template?",
        "lede": (
            "<code>GET /broadcast/match/{matchId}</code> returns ONE flat object for one match and "
            "<code>GET /broadcast/live</code> the same object for every live match in a single call. "
            "Both are ULTRA. A graphics template binds each field to a fixed path, so three things are "
            "contractual: the object is flat, every key is present on every read (<code>null</code>, "
            "never missing), and the score is already in display form — <code>p1_points</code> reads "
            "<code>\"40\"</code> or <code>\"AD\"</code> and <code>set_line</code> is one string. "
            "Built for 1 Hz: every response carries a strong <code>ETag</code>, so "
            "<code>If-None-Match</code> makes an unchanged state a 304 with no body. Detect a new state "
            "on <code>sequence</code>, never on <code>served_at</code>, which changes on every read."
        ),
        "paths": lambda p: p.startswith("/broadcast"),
    },
    {
        "slug": "push-feed-and-webhooks",
        "title": "Tennis WebSocket feed and webhooks",
        "question": "How do you receive tennis data as it happens instead of polling?",
        "lede": (
            "Two ways, both ULTRA. <code>GET /ws-token</code> mints a short-lived token for the "
            "high-fan-out push feed, which streams score and point changes as they are written. "
            "<code>POST /webhooks</code> registers an outbound HTTP callback for the same events; "
            "<code>GET /webhooks</code> lists your registrations and never returns the signing secret. "
            "Webhooks require a direct key, not a marketplace one."
        ),
        "paths": lambda p: p.startswith("/webhooks") or p == "/ws-token",
    },
    {
        "slug": "auth-quota-and-health",
        "title": "Tennis API authentication, quota and status",
        "head_title": "API authentication, quota and status — Live Tennis API",
        "question": "How do you authenticate, and how do you see what quota is left?",
        "description": (
            "How do you authenticate, and how do you see what quota is left? Send your key as "
            "X-API-Key on every request. GET /usage shows your headroom on every tier."
        ),
        "lede": (
            "Send your key as <code>X-API-Key</code> on every request. <code>GET /usage</code> returns "
            "your own consumption against your plan's quota and works on every tier including FREE, so "
            "a client can check its own headroom before a burst. <code>GET /health</code> is the "
            "unauthenticated liveness probe."
        ),
        "paths": lambda p: p in ("/usage", "/health"),
    },
]


def build_topic_pages(spec: dict[str, Any], reference_html: str) -> dict[str, str]:
    """{slug: html} — one page per topic, every operation rendered from the spec.

    Raises if any operation lands in no topic or in more than one. That is deliberate: the
    failure this guards against is a new endpoint quietly missing from the docs site, which
    is invisible in review because the reference page would still list it.
    """
    style_html = reference_base_style(reference_html)
    info = spec["info"]
    base = spec["servers"][0]["url"]

    assigned: dict[str, list[str]] = {}
    for path in spec["paths"]:
        hits = [t["slug"] for t in TOPICS if t["paths"](path)]
        assigned[path] = hits
    unmatched = [p for p, h in assigned.items() if not h]
    multi = {p: h for p, h in assigned.items() if len(h) > 1}
    if unmatched or multi:
        raise SystemExit(
            "TOPICS must cover every path exactly once.\n"
            + (f"  unmatched: {unmatched}\n" if unmatched else "")
            + (f"  matched more than once: {multi}\n" if multi else "")
            + "  Add or narrow a matcher in TOPICS (scripts/build_reference.py)."
        )

    pages = {}
    for topic in TOPICS:
        paths = [p for p in spec["paths"] if topic["paths"](p)]
        ops_html, op_count, tiers = [], 0, set()
        for path in paths:
            for method, op in spec["paths"][path].items():
                if method not in ("get", "post", "put", "patch", "delete"):
                    continue
                ops_html.append(render_operation(path, method, op, spec,
                                                 schema_href="./reference.html#"))
                tiers.add(tier_of(op.get("summary", "")))
                op_count += 1
        siblings = "\n".join(
            f'<a href="./{t["slug"]}.html">{E(t["title"])}</a>'
            for t in TOPICS + GUIDES if t["slug"] != topic["slug"]
        )
        plans = ", ".join(sorted(t for t in tiers if t)) or "FREE"
        # A meta description past ~160 characters is truncated in the result, so the tail is
        # wasted; the first crawl of these pages flagged every one of them at a flat 300, which
        # is what a bare [:300] slice looks like. Build it from the question plus whole
        # sentences of the lede until the budget runs out, so it always ends on a full stop.
        total_ops = sum(
            1 for pth in spec["paths"].values() for mth in pth
            if mth in ("get", "post", "put", "patch", "delete")
        )
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", topic["lede"])).strip()
        desc = topic["question"]
        for sentence in re.findall(r"[^.]+\.", plain):
            if len(desc) + 1 + len(sentence.strip()) > DESC_MAX:
                break
            desc = f"{desc} {sentence.strip()}"
        if len(desc) < DESC_MIN:
            # Whole sentences did not fill the budget — these ledes open with one long
            # sentence, so the loop above could add nothing. Use the space rather than waste
            # it: cut question + lede on a word boundary. A description trimmed mid-sentence
            # still reads; a 48-character one leaves two thirds of the result blank.
            full = f"{topic['question']} {plain}"
            desc = full
            # Measure the ESCAPED length: an apostrophe becomes &#x27; in the attribute, so a
            # 158-character cut can ship a 160-character description and trip the crawl check.
            while len(E(desc)) > DESC_MAX and " " in desc:
                desc = desc.rsplit(" ", 1)[0].rstrip(",;:")
            # A cut that lands on "and GET" or "match: the" reads as a typo in the result. Drop
            # the dangling connective, verb or article as well; the budget check below keeps
            # the result from falling under DESC_MIN unnoticed.
            while desc.rsplit(" ", 1)[-1].lower() in DANGLING and " " in desc:
                desc = desc.rsplit(" ", 1)[0].rstrip(",;:")
        if topic.get("description"):
            # Written by hand where the lede's sentences fit the budget badly: whole sentences
            # stop short of DESC_MIN and the word cut would end on a dangling preposition.
            desc = topic["description"]
        # The h1 is the topic title; the head title may be a shorter form of it, so that
        # "title — Live Tennis API" stays inside TITLE_MAX.
        head_title = topic.get("head_title") or f"{topic['title']} — {info['title']}"
        ld_json = tech_article_ld(topic["title"], desc, f"{DOCS_URL}/{topic['slug']}.html")
        pages[topic["slug"]] = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(head_title)}</title>
<meta name="description" content="{E(desc)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{DOCS_URL}/{topic['slug']}.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{E(topic['title'])}">
<meta property="og:url" content="{DOCS_URL}/{topic['slug']}.html">
<meta property="og:image" content="{DOCS_URL}/banner.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="favicon.ico" sizes="any">
<script type="application/ld+json">
{ld_json}
</script>
{FONT_PRELOADS}{INLINE_STYLES}
{style_html}{DESIGN_STYLES}
</head>
<body class="docs-page docs-topic">
<a class="skip-link" href="#main">Skip to content</a>
{site_navigation(topic['slug'])}
<div class="wrap">
<header>
<p class="meta">Live Tennis API &middot; docs &middot; version {E(str(info.get('version','')))}</p>
<h1>{E(topic['title'])}</h1>
<p><strong>{E(topic['question'])}</strong> {topic['lede']}</p>
<p class="meta">{op_count} endpoint{'s' if op_count != 1 else ''} on this page. Base URL
<code>{E(base)}</code>; authenticate with the <code>X-API-Key</code> header. Plans involved:
{E(plans)}. A free key needs no card.</p>
<nav class="pagenav" aria-label="Related pages">
<a href="./reference.html">Full reference — all endpoints</a>
<a href="./">Interactive reference</a>
<a href="./openapi.yaml">OpenAPI spec</a>
<a href="./changelog.html">Changelog</a>
<a href="{SITE}/pricing">Pricing</a>
<a href="{SITE}/subscribe/free">Free key</a>
</nav>
</header>
<main id="main">
<h2 id="endpoints">The endpoints</h2>
<p>Each one below lists its plan tier, every parameter, the response shape and an example. They
are the same entries as in <a href="./reference.html#endpoints">the full reference</a>, which
carries all {total_ops} operations of the API on one page.</p>
{"".join(ops_html)}
</main>
<footer>
<hr>
<nav class="pagenav" aria-label="Other topics">
{siblings}
</nav>
<p class="meta">Generated from <a href="./openapi.yaml">openapi.yaml</a> by
<a href="https://github.com/livetennisapi/openapi">livetennisapi/openapi</a>. Every endpoint on
this page is also in <a href="./reference.html">the full reference</a>.</p>
{CREDIT}
</footer>
</div>
{BEACON}{CLARITY}</body>
</html>
"""
    return pages


# ------------------------------------------------------------------ guides ---------------------
# Pages about a client package. A topic page covers a slice of the spec, a guide covers none.
# Guides share the topic pages' head, navigation and footer. Their body is written here, not
# generated from paths, so they sit outside the TOPICS rule that every path lands on one page.
#
# Every fact on the AI SDK page was checked against the published npm package
# (livetennisapi-ai 1.3.0) with ai 7.0.148 on 2026-10-22: the export names, the env var, the
# 25 tool names and their plans. Re-check them when the package changes its tool set.
AI_SDK_PACKAGE = "livetennisapi-ai"
AI_SDK_VERSION = "1.3.0"
# The day the page's facts were last checked against the package. It is the page's content
# date: the visible "Tested" line, JSON-LD dateModified and the sitemap lastmod all read it.
AI_SDK_CHECKED = "2026-10-22"
AI_SDK_NPM = "https://www.npmjs.com/package/livetennisapi-ai"
AI_SDK_REPO = "https://github.com/livetennisapi/livetennisapi-ai"

# (tool name, export, what it returns, plan). Names, exports and plans are the package's own.
# The "returns" column paraphrases the README table and each tool's description.
AI_SDK_TOOLS = [
    ("get_live_matches", "getLiveMatches", "Matches in progress, with live scores", "FREE"),
    ("get_upcoming_matches", "getUpcomingMatches", "Matches due to start soon", "FREE"),
    ("get_match", "getMatch", "Full detail for one match", "FREE"),
    ("get_match_score", "getMatchScore", "The score only, the lowest-latency read", "FREE"),
    ("search_players", "searchPlayers", "Find players by name", "FREE"),
    ("get_player", "getPlayer", "One player's profile and ranking", "FREE"),
    ("get_fixtures", "getFixtures", "The forward schedule", "FREE"),
    ("search_tournaments", "searchTournaments", "The tournament catalogue behind tournament_id", "FREE"),
    ("get_tournament", "getTournament", "One tournament by its stable id", "FREE"),
    ("check_api_status", "checkApiStatus", "Whether the API is up, and the plan it detects for the key", "FREE"),
    ("get_recent_results", "getRecentResults", "Completed matches with winners, filterable", "BASIC"),
    ("search_archive_matches", "searchArchiveMatches", "The results archive, 1968 to 2022", "BASIC"),
    ("get_archive_match", "getArchiveMatch", "One archive result, with serve stats where recorded", "BASIC"),
    ("search_archive_players", "searchArchivePlayers", "Archive bios: hand, date of birth, career-high rank", "BASIC"),
    ("get_archive_career", "getArchiveCareer", "Career win-loss, titles and serve totals over the archive", "BASIC"),
    ("get_h2h", "getH2H", "All-time head-to-head across the archive and recent matches", "BASIC"),
    ("get_match_events", "getMatchEvents", "Match timeline: breaks, games, momentum", "PRO"),
    ("get_match_odds", "getMatchOdds", "Match-winner market: bid, ask and mid", "PRO"),
    ("get_rankings", "getRankings", "Published ranking rows for one system, up to 200 per call", "PRO"),
    ("player_stats", "playerStats", "One player's record: W/L splits, tiebreaks, deciding sets, recent matches. Its serve_return block needs ULTRA", "PRO"),
    ("get_match_analysis", "getMatchAnalysis", "Model win probability and thesis", "ULTRA"),
    ("get_player_rankings", "getPlayerRankings", "Point-in-time rankings for specific players", "ULTRA"),
    ("get_match_statistics", "getMatchStatistics", "In-play statistics, derived and measured", "ULTRA"),
    ("get_charting_player", "getChartingPlayer", "A player's career shot-level charting profile", "ULTRA"),
    ("get_charting_match", "getChartingMatch", "Every charting stat family for one match", "ULTRA"),
]

AI_SDK_EXAMPLE = """import { generateText, gateway, isStepCount } from 'ai';
import { livetennisTools } from 'livetennisapi-ai';

const { text } = await generateText({
  model: gateway('openai/gpt-5-mini'),
  prompt: 'Which tennis matches are live right now, and what are the scores?',
  tools: livetennisTools(), // reads LIVETENNISAPI_KEY
  stopWhen: isStepCount(3),
});

console.log(text);"""

AI_SDK_SUBSET = """import { getLiveMatches, getMatchScore } from 'livetennisapi-ai';

const apiKey = process.env.LIVETENNISAPI_KEY;

const tools = {
  get_live_matches: getLiveMatches({ apiKey }),
  get_match_score: getMatchScore({ apiKey }),
};"""

AI_SDK_REFUSAL = """{
  ok: false,
  message: 'This data requires the ULTRA plan, and the configured API key is on a lower tier. ...'
}"""


def _ai_sdk_body(_spec: dict[str, Any] | None = None) -> str:
    plan_label = {"BASIC": "BASIC or any History plan"}
    rows = "".join(
        f"<tr><td><code>{E(name)}</code></td><td><code>{E(export)}</code></td>"
        f"<td>{E(does)}</td><td>{E(plan_label.get(plan, plan))}</td></tr>"
        for name, export, does, plan in AI_SDK_TOOLS
    )
    table = scrollx(
        f"<table>{vh_caption('The AI SDK tools, their exports and plans')}"
        '<thead><tr><th scope="col">Tool</th><th scope="col">Export</th>'
        '<th scope="col">Returns</th><th scope="col">Plan</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>",
        "AI SDK tools",
    )
    return f"""<h2 id="install">Install livetennisapi-ai</h2>
<p>The package is <a href="{AI_SDK_NPM}">{AI_SDK_PACKAGE}</a> on npm.
<code>ai</code> v7 is a peer dependency, so the tools use the copy your app already has. <code>ai</code> v7
needs Node 22 or later.</p>
<pre><code>npm install livetennisapi-ai ai
pnpm add livetennisapi-ai ai
yarn add livetennisapi-ai ai
bun add livetennisapi-ai ai</code></pre>

<h2 id="api-key">Set the API key</h2>
<p>The tools read your key from the <code>LIVETENNISAPI_KEY</code> environment variable.
<a href="{SITE}/subscribe/free">Get a free key</a>. No card is needed.</p>
<pre><code>export LIVETENNISAPI_KEY=twjp_...</code></pre>
<p>You can also pass the key in code as <code>livetennisTools({{ apiKey }})</code>. The
<code>apiKey</code> option wins over the environment variable. Each call returns a tool set bound to one key, so one
process can serve users on different plans.</p>

<h2 id="example">How do I use the tools with generateText?</h2>
<p>Pass the whole set as <code>tools</code>. This example goes through the AI Gateway, which reads
<code>AI_GATEWAY_API_KEY</code>. Any other AI SDK model that supports tool calling works in its place.</p>
<pre><code>{E(AI_SDK_EXAMPLE)}</code></pre>
<p><code>isStepCount(3)</code> gives the model room to call a tool and then answer.</p>

<h2 id="subset">Send only the tools you need</h2>
<p>Each tool is also exported on its own. Every tool's description and input schema go to the model
on every request, so a smaller set costs fewer tokens.</p>
<pre><code>{E(AI_SDK_SUBSET)}</code></pre>

<h2 id="tools">Which tools are there, and which plan does each need?</h2>
<p>Tool names, exports and plans are the ones the package defines. A tool above your key's plan
still answers. It explains which plan the data needs instead of returning it.</p>
{table}
<p>The tools call the REST endpoints documented on the <a href="./live-scores.html">live scores</a>,
<a href="./players-and-tournaments.html">players and tournaments</a>,
<a href="./historical-results-archive.html">results archive</a>, <a href="./tennis-odds.html">odds</a>
and <a href="./shot-level-rally-data.html">shot-level charting</a> pages.</p>
<p><code>check_api_status</code> answers even without a key. It calls <code>/health</code>, then reads
the key's plan from <code>/usage</code> and reports that plan. A FREE key with History access reports as
FREE. When a temporary grant lifts the key above its subscription, the message says so and names the
subscription and the expiry. That is the quickest way to find out why another tool declined.
If <code>/usage</code> cannot be read, the tool falls back to probing a few endpoints and reports an
estimate. In that fallback a FREE key with History access reads as BASIC. Plans and prices are on the
<a href="{SITE}/pricing">pricing page</a>.</p>
<h2 id="results">What happens when a tool can't return data?</h2>
<p>A successful call returns <code>ok: true</code>, a readable <code>message</code> and the data.
An empty answer is still a success, for example <code>ok: true</code> with no live matches.
A missing or rejected key, a plan limit, a rate limit, an unknown id or a failed request returns
<code>ok: false</code>. The <code>message</code> says what to do next.</p>
<pre><code>{E(AI_SDK_REFUSAL)}</code></pre>
<p>No tool throws for these. The model reads the message and can pass the upgrade path or the
wait time on to the user.</p>

<h2 id="mcp">Can I use the same tools over MCP?</h2>
<p>The same 25 tools also run as an MCP server. The hosted endpoint is
<code>https://mcp.livetennisapi.com/mcp</code>. Send your key as
<code>Authorization: Bearer twjp_...</code>. To run it yourself, use
<code>npx livetennisapi-mcp</code> from <a href="https://github.com/livetennisapi/livetennisapi-mcp">livetennisapi/livetennisapi-mcp</a>.</p>

<h2 id="links">Links</h2>
<ul>
<li><a href="{AI_SDK_NPM}">livetennisapi-ai on npm</a></li>
<li><a href="{AI_SDK_REPO}">Source on GitHub</a></li>
<li><a href="{SITE}/subscribe/free">Free API key</a></li>
<li><a href="./auth-quota-and-health.html">Authentication, quota and status</a></li>
</ul>
"""


# ----------------------------------------------------------------- errors and rate limits -------
# The errors guide is half generated, half written. Generated from the spec at build time: which
# status codes exist, which shared response each one uses, the operations that name each error
# code, and the per-tier limits. Written here: what causes each code and what a client should do.
# The build fails when the two drift apart (see _errors_drift).
#
# The retry section describes the official clients as published, read on ERRORS_CHECKED:
# livetennisapi 1.8.0 on PyPI (_base.py _should_retry, _retryable, _backoff) and livetennisapi
# 1.10.2 on npm (client.ts shouldRetry, backoff, request). Both were also run against a local
# server answering each status in turn. Re-check them when either client changes its retry code.
ERRORS_CHECKED = "2026-11-09"
ERRORS_PY_VERSION = "1.8.0"
ERRORS_JS_VERSION = "1.10.2"
PY_REPO = "https://github.com/livetennisapi/livetennisapi-python"
JS_REPO = "https://github.com/livetennisapi/livetennisapi-js"

# Every code the REST spec names, by status: (codes, cause, what to do). Causes paraphrase the
# spec text that defines the code. The operations column is not typed here: it is read from the
# spec, so a code that moves to another endpoint moves on the page too.
ERROR_CODES: list[tuple[int, tuple[str, ...], str, str]] = [
    (400, ("bad_status",), "<code>status</code> is not one of the accepted values.",
     "Use a value from <code>allowed</code> in the body."),
    (400, ("bad_request",), "A non-integer <code>player</code> id, or <code>updated_since</code> sent "
     "with <code>status=cancelled</code>.", "Fix the parameter."),
    (400, ("bad_updated_since",), "<code>updated_since</code> sent together with <code>from</code> or "
     "<code>to</code>.", "Send one or the other."),
    (400, ("bad_withdrawn_since",), "<code>withdrawn_since</code> sent with any parameter other than "
     "<code>limit</code> and <code>offset</code>, or with an instant that does not parse.",
     "Send it alone, as an ISO-8601 instant."),
    (400, ("bad_has_analysis", "bad_has_market", "bad_is_qualifying", "bad_points_complete"),
     "The flag was something other than <code>true</code> or <code>false</code>.",
     "Send <code>true</code> or <code>false</code>."),
    (400, ("bad_gender",), "A value other than <code>men</code> or <code>women</code>.", "Fix the value."),
    (400, ("bad_country",), "A country value that is not 3 letters.", "Send a 3-letter code."),
    (400, ("bad_draw", "bad_coverage"), "An unknown value.",
     "Use a value from <code>allowed</code> in the body."),
    (400, ("bad_tier",), "An unknown tier value. The body names the refused values in <code>bad</code>.",
     "Use a value from <code>allowed</code> in the body."),
    (400, ("bad_tournament_id",), "A non-numeric <code>tournament_id</code>.", "Send the numeric id."),
    (400, ("bad_restated_since", "bad_changed_since"), "The value is not an ISO-8601 instant. A bare date "
     "is refused for <code>restated_since</code>, because a day is not an instant.",
     "Send a full UTC timestamp."),
    (400, ("bad_date", "bad_surface", "bad_level", "bad_last"), "A rejected query on player stats. "
     "<code>bad_surface</code> and <code>bad_level</code> list the accepted values in "
     "<code>allowed</code>.", "Fix the parameter named by the code."),
    (400, ("doubles_not_supported",), "A doubles-team id on player stats.", "Ask for a singles player id."),
    (400, ("bad_sequence",), "On the tape, a <code>sequence</code> other than <code>raw</code> or "
     "<code>clean</code>. On the score endpoint, a <code>sequence</code> that is not an integer.",
     "Fix the value."),
    (400, ("bad_points",), "An unknown <code>points</code> value.",
     "Send <code>default</code> or <code>complete</code>."),
    (400, ("bad_combination",), "<code>points=complete</code> together with <code>sequence=clean</code>.",
     "Drop one of the two."),
    (400, ("points_read_disabled",), "<code>points=complete</code> where that read is not enabled yet.",
     "Use the default read. Repeating the same request gets the same answer."),
    (400, ("points_disabled",), "The per-point surface is switched off on the server.",
     "Stop polling it. A retry gets the same answer while it is off."),
    (400, ("bad_after_seq",), "<code>after_seq</code> is not a non-negative integer.",
     "Send the <code>last_seq</code> of the previous page."),
    (400, ("bad_cursor",), "A malformed cursor.",
     "Send the cursor exactly as the previous page returned it."),
    (400, ("bad_type", "bad_after_id"), "A refused <code>type</code> or <code>after_id</code> on the "
     "events feed.", "Take <code>after_id</code> from <code>meta.next_cursor</code>. Send event "
     "types or <code>stoppages</code> as <code>type</code>."),
    (400, ("bad_since", "bad_until", "bad_window", "bad_kind"), "A refused time bound, window or kind.",
     "Fix the parameter named by the code."),
    (400, ("window_too_long",), "A stoppage or injury window longer than 366 days.",
     "Split the request into shorter windows."),
    (400, ("bad_format",), "<code>format</code> was neither <code>jsonl</code> nor <code>csv</code>.",
     "Send <code>jsonl</code> or <code>csv</code>."),
    (400, ("bad_period",), "The period is not <code>YYYY-MM</code>, or not <code>YYYY</code> for the "
     "yearly kinds (<code>rally</code>, <code>archive</code>, <code>elo</code>, "
     "<code>archive_tape</code>).", "Fix the period format."),
    (400, ("ambiguous_name",), "A name fragment matched more than one player. The body lists the "
     "candidates.", "Send a player id, or a longer name."),
    (403, ("upgrade_required",), "The key is valid and the plan does not include this data. "
     "<code>free_history_taste: \"used\"</code> means a FREE key has spent its 20 history calls for "
     "the calendar month. <code>capability: archive_tape</code> means a core BASIC or PRO key asked "
     "for the archive tape.", f'Upgrade the plan (<a href="{SITE}/pricing">pricing</a>). Retrying '
     "does not help."),
    (404, ("not_found",), "No such id. On the player routes the body adds <code>detail</code> and "
     "<code>see</code> when the id belongs to the results archive.",
     "Check the id. If <code>see</code> is present, read the archive lookup it names."),
    (404, ("no_analysis",), "The match exists and nothing has been computed for it. The body carries "
     "<code>match_id</code> and <code>coverage: \"none\"</code>.",
     "Filter the slate with <code>has_analysis=true</code> instead of probing each match."),
    (404, ("no_market",), "The match exists and no match-winner market is mapped to it.",
     "Filter with <code>has_market=true</code> instead of probing each match."),
    (404, ("not_charted",), "We hold the match and nobody charted it.",
     "Treat it as uncharted. Most matches are."),
    (404, ("not_derivable",), "The incident has no exact per-match derivation. The body carries its "
     "<code>window_utc</code>, <code>affected_surfaces</code> and a note saying why.",
     "Use the window and surfaces in the body."),
    (409, ("webhook_limit",), "The key already has 3 webhooks.", "Delete one before adding another."),
    (410, ("merged",), "The id was merged into another record, or a player id was retired.",
     "Replace the stored id with <code>merged_into</code>. If it is null, drop the id."),
    (429, ("rate_limited",), "The per-minute window, or with <code>scope: \"day\"</code> the daily quota.",
     'See <a href="#rate-limits">the 429 section</a>.'),
    (429, ("abuse_throttled",), "A 24-hour block for a client that kept calling far past its cap.",
     "Fix the retry loop. Do not retry until <code>retry_at_epoch</code>."),
    (503, ("coverage_unavailable",), "The coverage rollup has not been built yet, or cannot be read.",
     "Try again after the nightly build."),
]
# Codes that come with a shared response: the page names the response and how many operations
# use it, read from the spec, beside any operation that names the code in its own text.
ERROR_CODE_RESPONSES = {
    "upgrade_required": ("UpgradeRequired",),
    "rate_limited": ("RateLimited",),
    "abuse_throttled": ("RateLimited",),
    "merged": ("MatchGone", "PlayerGone"),
}
# Named in the Error schema's code list with no endpoint or status attached to them.
ERROR_CODES_UNPLACED = ("bad_tour", "bad_year")
# WebSocket refusals, from the close-code section of info.description: (close code, codes, action).
WS_CLOSE_CODES = [
    ("1013", ("connection_limit", "service_unavailable"),
     "Transient. Back off and reconnect. For <code>connection_limit:per_key</code>, close a connection "
     "first or move to the push feed."),
    ("1008", ("unauthorized", "upgrade_required", "email_unverified", "client_blocked", "bad_json",
              "no_topics"), "The request will never be accepted as sent. Fix it, do not retry unchanged."),
    ("1012", (), "The server is restarting. Reconnect with backoff and subscribe again."),
    ("1000", (), "Normal closure: you closed it, or the stream ended."),
]

# What each status means and what to do. The "defined in" column is read from the spec.
STATUS_ACTIONS: dict[int, tuple[str, str]] = {
    304: ("Not an error. The broadcast state is unchanged since the <code>ETag</code> you sent.",
          "Keep the copy you have."),
    400: ("A query parameter was refused. The <code>error</code> code names it.", "Fix the request."),
    401: ("The key is missing, unknown or disabled.", "Send a valid key. Re-authenticate."),
    403: ("The key works and the plan does not include this data.", "Upgrade the plan."),
    404: ("No such resource, or no data for it yet.", "Check the id, or use the availability flags."),
    409: ("The webhook limit is reached.", "Delete a webhook first."),
    410: ("The id was merged or retired. The body forwards you.", "Re-point to <code>merged_into</code>."),
    429: ("A rate limit or quota was hit.", "Depends on the body. See below."),
    503: ("<code>/history/coverage</code> is not built yet.", "Try again later."),
}

# Client retry behaviour, one row per answer the API can give. Python and JS behave the same.
CLIENT_RETRY_ROWS = [
    ("429 <code>rate_limited</code>, per-minute window", "Yes",
     "Waits <code>Retry-After</code> if sent, else exponential backoff"),
    ("Any 5xx", "Yes", "Waits <code>Retry-After</code> if sent, else exponential backoff"),
    ("Connection error or timeout", "Yes", "Exponential backoff"),
    ("429 <code>rate_limited</code> with <code>scope: \"day\"</code>", "No", "Raises at once"),
    ("429 <code>abuse_throttled</code>", "No", "Raises at once"),
    ("400, 401, 403, 404 and every other 4xx", "No", "Raises at once"),
]
CLIENT_EXCEPTIONS = [
    ("400", "BadRequest"), ("401", "Unauthorized"), ("403", "UpgradeRequired"), ("404", "NotFound"),
    ("429", "RateLimited"), ("429 <code>abuse_throttled</code>", "AbuseThrottled"),
    ("503", "ServiceUnavailable"), ("Other 5xx", "ServerError"),
    ("409, 410 and other statuses", "APIStatusError"),
]

_CODE_TOKEN = re.compile(
    r"\b(bad_[a-z_]+|[a-z]+(?:_[a-z]+)*_(?:disabled|not_supported|unavailable|too_long|limit)"
    r"|ambiguous_name|not_charted|not_found|no_analysis|no_market|not_derivable"
    r"|upgrade_required|rate_limited|abuse_throttled)\b"
)
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def _texts(node: Any) -> list[str]:
    if isinstance(node, dict):
        return [t for v in node.values() for t in _texts(v)]
    if isinstance(node, list):
        return [t for v in node for t in _texts(v)]
    return [node] if isinstance(node, str) else []


def _op_texts(op: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """The operation's own prose: description, parameters (shared ones resolved) and response
    descriptions. Response schemas stay out: every error response embeds the Error schema, whose
    description lists the whole code vocabulary, and would make every operation name every code."""
    out = _texts({k: v for k, v in op.items() if k not in ("parameters", "responses", "requestBody")})
    for item in op.get("parameters") or []:
        out += _texts(resolve(item, spec))
    for resp in (op.get("responses") or {}).values():
        if "$ref" in resp:
            resp = resolve({"$ref": resp["$ref"]}, spec)
        out.append(resp.get("description", ""))
    return out


def error_code_sources(spec: dict[str, Any]) -> dict[str, list[str]]:
    """{code: ["GET /path", ...]}: the operations whose own text names the code."""
    found: dict[str, list[str]] = {}
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method not in _HTTP_METHODS:
                continue
            codes = {c for t in _op_texts(op, spec) for c in _CODE_TOKEN.findall(t)}
            for code in codes:
                found.setdefault(code, []).append(f"{method.upper()} {path}")
    return found


def error_statuses(spec: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """{status: {"refs": {component: operation count}, "inline": [operations]}} for non-2xx."""
    out: dict[int, dict[str, Any]] = {}
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method not in _HTTP_METHODS:
                continue
            for code, resp in (op.get("responses") or {}).items():
                status = int(code)
                if 200 <= status < 300:
                    continue
                slot = out.setdefault(status, {"refs": {}, "inline": []})
                ref = resp.get("$ref", "")
                if ref:
                    name = ref.rsplit("/", 1)[-1]
                    slot["refs"][name] = slot["refs"].get(name, 0) + 1
                else:
                    slot["inline"].append(f"{method.upper()} {path}")
    return dict(sorted(out.items()))


_TIER_LIMIT_RX = re.compile(r"`(FREE|BASIC|PRO|ULTRA)`.*?([\d,]+) requests/minute, ([\d,]+)/day", re.S)


def tier_limits(spec: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(tier, per minute, per day), read from info.description. Fails the build if one is missing."""
    found = {}
    for block in re.split(r"\n\s*\n", spec["info"]["description"]):
        m = _TIER_LIMIT_RX.search(block)
        if m and m.group(1) not in found:
            found[m.group(1)] = (m.group(1), m.group(2), m.group(3))
    missing = [t for t in TIER_ORDER_ALL if t not in found]
    if missing:
        raise SystemExit(f"errors guide: no per-minute/per-day limits found in info for {missing}")
    return [found[t] for t in TIER_ORDER_ALL]


TIER_ORDER_ALL = ("FREE", "BASIC", "PRO", "ULTRA")


def _errors_drift(spec: dict[str, Any]) -> None:
    """Fail the build when the written half of the errors guide disagrees with the spec."""
    spec_text = "\n".join(_texts(spec))
    tokens = set(re.findall(r"[a-z_]+", spec_text))
    listed = {c for _, codes, _, _ in ERROR_CODES for c in codes}
    problems = []
    # Every code on the page is spelled exactly as the spec spells it.
    for code in sorted(listed | set(ERROR_CODES_UNPLACED)):
        if code not in tokens:
            problems.append(f"{code} is on the page and nowhere in the spec")
    ws_codes = {c for _, codes, _ in WS_CLOSE_CODES for c in codes}
    info_tokens = set(re.findall(r"[a-z_]+", spec["info"]["description"]))
    for code in sorted(ws_codes - info_tokens):
        problems.append(f"WebSocket code {code} is not in info.description")
    # Every code the REST surface names is on the page.
    rest = _texts(spec["paths"]) + _texts(spec["components"])
    named = {c for t in rest for c in _CODE_TOKEN.findall(t)}
    for code in sorted(named - listed - set(ERROR_CODES_UNPLACED)):
        problems.append(f"{code} is named in the spec and missing from ERROR_CODES")
    # Every non-2xx status the spec documents has a row, and nothing else does.
    statuses = set(error_statuses(spec))
    for status in sorted(statuses ^ set(STATUS_ACTIONS)):
        problems.append(f"status {status}: in the spec {status in statuses}, on the page "
                        f"{status in STATUS_ACTIONS}")
    for status in {s for s, _, _, _ in ERROR_CODES} - statuses:
        problems.append(f"ERROR_CODES uses status {status}, which the spec does not document")
    used = {name for slot in error_statuses(spec).values() for name in slot["refs"]}
    for code, names in ERROR_CODE_RESPONSES.items():
        for name in names:
            if name not in used:
                problems.append(f"{code}: no operation uses the response {name}")
    if problems:
        raise SystemExit("errors guide out of step with the spec:\n  " + "\n  ".join(problems))


def _ops_cell(ops: list[str], limit: int = 4) -> str:
    if len(ops) > 2 * limit:
        return f"{len(ops)} operations"
    shown = "<br>".join(f"<code>{E(o)}</code>" for o in ops[:limit])
    if len(ops) > limit:
        shown += f"<br>and {len(ops) - limit} more"
    return shown


def _errors_body(spec: dict[str, Any]) -> str:
    _errors_drift(spec)
    statuses = error_statuses(spec)
    sources = error_code_sources(spec)
    used = {name: n for slot in statuses.values() for name, n in slot["refs"].items()}

    status_rows = []
    for status, slot in statuses.items():
        defined = [f"<code>{E(name)}</code> ({n} operation{'s' if n != 1 else ''})"
                   for name, n in slot["refs"].items()]
        defined += [f"inline on <code>{E(op)}</code>" for op in slot["inline"]]
        meaning, action = STATUS_ACTIONS[status]
        retried = "Yes" if status >= 500 else ("Per-minute only" if status == 429 else "No")
        status_rows.append(
            f"<tr><td><code>{status}</code></td><td>{meaning}</td><td>{action}</td>"
            f"<td>{retried}</td><td>{'<br>'.join(defined)}</td></tr>\n"
        )
    status_table = scrollx(
        f"<table>{vh_caption('Every non-2xx status the spec documents')}"
        '<thead><tr><th scope="col">Status</th><th scope="col">Meaning</th>'
        '<th scope="col">What to do</th><th scope="col">Clients retry</th>'
        '<th scope="col">Defined in the spec</th></tr></thead>'
        f"<tbody>\n{''.join(status_rows)}</tbody></table>",
        "Status codes",
    )

    def code_table(wanted: set[int], caption: str) -> str:
        rows = []
        for status, codes, cause, action in ERROR_CODES:
            if status not in wanted:
                continue
            ops = sorted({o for c in codes for o in sources.get(c, [])})
            shared = [
                f"every <code>{E(name)}</code> response ({used[name]} operations)"
                for c in codes for name in ERROR_CODE_RESPONSES.get(c, ())
            ]
            if shared and len(ops) > 8:
                ops = []  # every user of the shared response: the response line says it once
            parts = ([_ops_cell(ops)] if ops else []) + shared
            where = "<br>".join(parts) or "The <code>Error</code> schema"
            rows.append(
                f"<tr><td><code>{status}</code></td><td>"
                + "<br>".join(f"<code>{E(c)}</code>" for c in codes)
                + f"</td><td>{cause}</td><td>{action}</td><td>{where}</td></tr>\n"
            )
        return scrollx(
            f"<table>{vh_caption(caption)}"
            '<thead><tr><th scope="col">Status</th><th scope="col"><code>error</code></th>'
            '<th scope="col">Cause</th><th scope="col">What to do</th>'
            '<th scope="col">Named in the spec on</th></tr></thead>'
            f"<tbody>\n{''.join(rows)}</tbody></table>",
            caption,
        )

    limits = "".join(
        f"<tr><td>{tier}</td><td>{minute}</td><td>{day}</td></tr>\n"
        for tier, minute, day in tier_limits(spec)
    )
    limits_table = scrollx(
        f"<table>{vh_caption('Requests per minute and per day by plan')}"
        '<thead><tr><th scope="col">Plan</th><th scope="col">Per minute</th>'
        '<th scope="col">Per day</th></tr></thead>'
        f"<tbody>\n{limits}</tbody></table>",
        "Rate limits by plan",
    )
    retry_rows = "".join(
        f"<tr><td>{answer}</td><td>{retried}</td><td>{how}</td></tr>\n"
        for answer, retried, how in CLIENT_RETRY_ROWS
    )
    retry_table = scrollx(
        f"<table>{vh_caption('What the official clients retry')}"
        '<thead><tr><th scope="col">The API answers</th><th scope="col">Retried</th>'
        '<th scope="col">How</th></tr></thead>'
        f"<tbody>\n{retry_rows}</tbody></table>",
        "Client retries",
    )
    exc_rows = "".join(
        f"<tr><td>{status}</td><td><code>{name}</code></td></tr>\n" for status, name in CLIENT_EXCEPTIONS
    )
    exc_table = scrollx(
        f"<table>{vh_caption('Error classes in both clients')}"
        '<thead><tr><th scope="col">Status</th><th scope="col">Class (Python and JS)</th></tr></thead>'
        f"<tbody>\n{exc_rows}</tbody></table>",
        "Client error classes",
    )
    ws_rows = "".join(
        f"<tr><td><code>{code}</code></td><td>"
        + ("<br>".join(f"<code>{c}</code>" for c in codes) or "None")
        + f"</td><td>{action}</td></tr>\n"
        for code, codes, action in WS_CLOSE_CODES
    )
    ws_table = scrollx(
        f"<table>{vh_caption('WebSocket close codes')}"
        '<thead><tr><th scope="col">Close code</th><th scope="col">Reasons</th>'
        '<th scope="col">What to do</th></tr></thead>'
        f"<tbody>\n{ws_rows}</tbody></table>",
        "WebSocket close codes",
    )
    unplaced = " and ".join(f"<code>{c}</code>" for c in ERROR_CODES_UNPLACED)

    return f"""<h2 id="body">What does an error response look like?</h2>
<p>Every error is JSON. Most use the <code>Error</code> schema:</p>
<ul>
<li><code>error</code>: a stable machine-readable code. Branch on this, never on the text.</li>
<li><code>detail</code>: a human-readable explanation, when one adds anything.</li>
<li><code>allowed</code>: on a refused enumerated parameter, the values that would have been accepted.</li>
</ul>
<p>Two other shapes exist. A 410 carries <code>MatchMerged</code> or <code>PlayerMerged</code>:
<code>error: "merged"</code>, <code>merged_into</code>, <code>merged_at</code> and <code>detail</code>.
A 404 on <code>/players/{{playerId}}</code> and its stoppage and injury routes carries
<code>PlayerNotFound</code>. It adds <code>detail</code> and <code>see</code> when the id belongs
to the results archive. Some codes add their own fields, named in the tables below.</p>
<pre><code>{E('{"error": "upgrade_required"}')}</code></pre>

<h2 id="statuses">Which status codes can the API return?</h2>
<p>These are all the non-2xx statuses in the OpenAPI spec, read from it when this page is built.
Every endpoint except <code>/health</code>, which takes no key, documents 401.</p>
{status_table}
<p>The spec documents no other 5xx. The official clients treat any 5xx they get as temporary and
retry it.</p>

<h2 id="bad-request">Which 400 codes are there?</h2>
<p>A 400 is never retried. The request is wrong as sent and gets the same answer every time.
The last column lists the operations whose spec text names the code.</p>
{code_table({400}, "400 error codes")}
<p>The <code>Error</code> schema also lists {unplaced}. The spec does not say which endpoint
returns them.</p>

<h2 id="auth-and-plan">401 or 403: is it the key or the plan?</h2>
<p>A 401 means the key itself failed: it is missing, unknown or disabled. Send it as
<code>Authorization: Bearer &lt;key&gt;</code>, <code>X-API-Key: &lt;key&gt;</code> or
<code>?token=&lt;key&gt;</code>. A 403 means the key works and the plan stops short of the data.
It is never a silent empty result.</p>
{code_table({403}, "403 error codes")}
<p>The 403 body names no tier. The Python client's <code>UpgradeRequired.required_tier</code> and
the JS client's <code>requiredTier</code> work out the lowest tier from the endpoint you called.</p>

<h2 id="not-found">What does a 404 or 410 mean for a stored id?</h2>
{code_table({404, 409, 410}, "404, 409 and 410 error codes")}
<p>Two 404s carry no code of their own. <code>GET /matches/{{matchId}}/score</code> answers 404
for an unknown match or an upcoming match with no score yet. It does the same for a cancelled
match that was never played, and for a settled match with nothing recorded.</p>
<p>The archive tape answers a plain 404 for a result from 1968 to 2012. So does a 2013 to 2022
result that was never reconstructed, or one whose reconstruction did not prove its binding.
The three are not told apart.</p>
<p>A 410 is only ever about an id that once existed. An id that was never issued stays a 404.</p>

<h2 id="rate-limits">What does a 429 mean, and when do I retry it?</h2>
<p>Every 429 carries a <code>Retry-After</code> header. The body tells you which of three limits
you hit, and only the first is worth retrying.</p>
<ol>
<li><strong>Per-minute window.</strong> <code>error: "rate_limited"</code> with no <code>scope</code>.
The body names the next tier up in <code>upgrade_url</code>, <code>tier</code> and
<code>price</code>. Wait <code>Retry-After</code> seconds and send the request again.</li>
<li><strong>Daily quota.</strong> <code>error: "rate_limited"</code> with <code>scope: "day"</code>,
<code>limit_per_day</code> and <code>resets_at</code>, the ISO instant the daily window resets.
Do not retry. Stop until <code>resets_at</code>, or upgrade.</li>
<li><strong>Abuse throttle.</strong> <code>error: "abuse_throttled"</code> with
<code>retry_at_epoch</code>. A 24-hour block for a client that keeps calling far past its cap.
A retry loop that backs off never sees it. Fix the loop and wait until
<code>retry_at_epoch</code>.</li>
</ol>
{code_table({429, 503}, "429 and 503 error codes")}
<p>The official clients retry a 503 like any 5xx and give up after 2 retries. The coverage
rollup is built nightly, so for <code>coverage_unavailable</code> check again later.</p>

<h2 id="clients">How do the official clients retry?</h2>
<p>The <a href="{PY_REPO}">Python client</a> ({ERRORS_PY_VERSION}) and the
<a href="{JS_REPO}">JS client</a> ({ERRORS_JS_VERSION}) follow the same rules. We read both from
source and ran them against a local server on
<time datetime="{ERRORS_CHECKED}">{ERRORS_CHECKED}</time>.</p>
{retry_table}
<ul>
<li>Up to 2 retries by default, so 3 attempts in all. Set <code>max_retries</code> in Python or
<code>maxRetries</code> in JS. 0 turns retries off.</li>
<li>With <code>Retry-After</code>, the wait is that many seconds, at most 60.</li>
<li>Without it, the wait is 0.5 s doubled on each attempt plus up to 0.25 s of random jitter,
at most 10 s. The jitter keeps many clients from retrying in step.</li>
<li>When the retries run out, the client raises the error for the last answer.</li>
</ul>
{exc_table}
<p>In both clients <code>RateLimited</code> carries <code>retry_after</code> (Python) or
<code>retryAfter</code> (JS), and <code>resets_at</code> or <code>resetsAt</code> on a daily 429.
<code>AbuseThrottled</code> carries <code>retry_at_epoch</code> or <code>retryAtEpoch</code>.</p>

<h2 id="own-client">How should my own client back off?</h2>
<p>Do what the official clients do. Retry a 429 only when the body has no <code>scope: "day"</code>
and the code is not <code>abuse_throttled</code>. Retry a 5xx or a dropped connection. Wait
<code>Retry-After</code> when it is sent, and otherwise back off exponentially with jitter. Cap the
number of retries. Never retry a 400, 401, 403, 404, 409 or 410 unchanged.</p>

<h2 id="limits">What are the limits on each plan?</h2>
<p>Read from the spec. Each plan includes everything in the plans below it.</p>
{limits_table}
<p><code>GET /usage</code> returns your plan, your limits and today's calls, and calling it never
uses quota. Refused requests do not spend the daily allowance, so <code>remaining_day</code> does
not fall on a 429, 403 or 404. The per-minute window is on the <code>X-RateLimit-*</code> headers
of every response. Plans and prices are on the <a href="{SITE}/pricing">pricing page</a>.</p>

<h2 id="websocket">What do the WebSocket close codes mean?</h2>
<p>The WebSocket feed sends an <code>error</code> frame, then closes with a code that says what to
do next. The close reason repeats the frame's <code>error</code>.</p>
{ws_table}

<h2 id="links">Links</h2>
<ul>
<li><a href="./auth-quota-and-health.html">Authentication, quota and status</a></li>
<li><a href="./reference.html">Full reference, every endpoint and response</a></li>
<li><a href="{PY_REPO}">livetennisapi for Python</a> and <a href="{JS_REPO}">livetennisapi for JS</a></li>
<li><a href="{SITE}/subscribe/free">Free API key</a></li>
</ul>
"""


# ----------------------------------------------------------------- export formats ---------------
# Every fact on the export page comes from the published package, livetennisapi-export 0.1.0 on
# PyPI, read on EXPORT_CHECKED: datasets.py (the six datasets, their endpoints, plans and paging),
# writers.py (flatten, the CSV and Parquet rules), cli.py (exit codes, the key variable) and the
# tests. The read-back snippets were run on that day against files written by the package's own
# writers: pandas 3.1.1 with pyarrow 26.0.1, DuckDB 2.0.0, and R 4.6.2 with arrow 26.0.1.
# Re-check the page when the package changes its datasets or its writers.
EXPORT_PACKAGE = "livetennisapi-export"
EXPORT_VERSION = "0.1.0"
EXPORT_CHECKED = "2026-11-11"
EXPORT_PYPI = "https://pypi.org/project/livetennisapi-export/"
EXPORT_REPO = "https://github.com/livetennisapi/livetennisapi-export"
# The package's MAX_PAGE_SIZE. _export_drift holds it against the spec's `limit` maximum.
EXPORT_PAGE_SIZE = 200

# (dataset, spec path, how the page shows the endpoint, plan in the package's words, requests).
EXPORT_DATASETS = [
    ("matches", "/matches", "GET /matches",
     "FREE for <code>live</code> and <code>upcoming</code>. <code>completed</code> and "
     "<code>cancelled</code> are part of History and need BASIC or a History plan",
     "One per page"),
    ("fixtures", "/fixtures", "GET /fixtures", "FREE", "One per page"),
    ("players", "/players", "GET /players?search=", "FREE", "One per page"),
    ("player", "/players/{playerId}", "GET /players/{playerId}", "FREE", "One per player id"),
    ("rankings", "/rankings", "GET /rankings",
     "PRO. <code>--system elo</code> needs ULTRA", "One per page"),
    ("tournaments", "/tournaments", "GET /tournaments", "FREE", "One per page"),
]

# (format, file names, what a row looks like, when it fits).
EXPORT_FORMATS = [
    ("CSV", "<code>.csv</code>",
     "Flat columns, one header line, every value as text",
     "You want to open the file in a spreadsheet or load it into a tool that reads nothing else."),
    ("JSON Lines", "<code>.jsonl</code> or <code>.ndjson</code>",
     "One JSON object per line, exactly as the API returned it, nested objects included",
     "You want the record unchanged, for a pipeline, a document store or a later reshape."),
    ("Parquet", "<code>.parquet</code> or <code>.pq</code>",
     "Flat columns with a type per column",
     "You analyse the data in pandas, DuckDB or R and want numbers and booleans to stay typed."),
]

EXPORT_COMMANDS = """# Upcoming fixtures on the ATP tour
livetennisapi-export fixtures --tour atp -o fixtures.csv

# Every match completed on one day, as Parquet
livetennisapi-export matches --status completed --date 2026-11-08 -o results.parquet

# The same day as JSON Lines, rows unchanged
livetennisapi-export matches --status completed --date 2026-11-08 -o results.jsonl

# Full profiles for a list of player ids
livetennisapi-export player 101 202 303 -o players.csv

# The current ATP ranking table
livetennisapi-export rankings --system atp -o atp.csv

# Player search, written to stdout
livetennisapi-export players alcaraz -o - -f jsonl"""

# A match row cut down to six fields. The values are the made-up ones from the package's tests.
EXPORT_NESTED = """{"id": 5001, "tournament": "Example Open",
 "players": {"p1": {"name": "Test Player A", "ranking": 12}},
 "score": {"sets": [2, 0], "games": [[6, 6], [3, 4]]}}"""

# (column, value in the CSV) for EXPORT_NESTED, as writers.flatten produces them.
EXPORT_FLAT = [
    ("id", "5001"),
    ("tournament", "Example Open"),
    ("players.p1.name", "Test Player A"),
    ("players.p1.ranking", "12"),
    ("score.sets", "[2, 0]"),
    ("score.games", "[[6, 6], [3, 4]]"),
]

# (export, spec schema of a row, some of its columns). Every name is a field the spec documents
# at that path. _export_drift resolves each one against the schema and fails the build otherwise.
EXPORT_SEEN = [
    ("fixtures, as CSV", "Fixture", ["id", "event_date", "start_time", "player1_id", "player1_name",
                                     "player2_id", "player2_name", "tournament"]),
    ("matches, completed, as Parquet", "Match", ["players.p1.itf_ranking.rank_date", "score.timestamp"]),
    ("rankings, <code>--system atp</code>", "RankingRecord",
     ["effective_date", "observed_at", "player_id", "player_name", "points", "previous_rank", "rank",
      "rank_movement"]),
]

EXPORT_PANDAS = """import json
import pandas as pd

results = pd.read_parquet("results.parquet")
print(results[["tournament", "round", "players.p1.name", "players.p2.name", "winner"]])

# Lists are stored as JSON text. Decode a column when you need the values.
results["sets"] = results["score.sets"].map(json.loads, na_action="ignore")

fixtures = pd.read_csv("fixtures.csv", parse_dates=["event_date"])
print(fixtures.groupby("tournament")["id"].count())"""

EXPORT_DUCKDB = """-- A dotted column needs double quotes in CSV and Parquet files.
SELECT tournament, "players.p1.name", "players.p2.name", winner
FROM 'results.parquet'
WHERE surface = 'hard';

-- Lists are JSON text. Cast one to read it as a list.
SELECT id, CAST("score.sets" AS INTEGER[]) AS sets
FROM 'results.parquet';

-- JSON Lines keeps the nesting, so the same field is a struct path.
SELECT tournament, players.p1.name, score.sets
FROM read_json_auto('results.jsonl');

SELECT rank, player_name, points
FROM 'atp.csv'
ORDER BY rank;"""

EXPORT_R = """fixtures <- read.csv("fixtures.csv")
table(fixtures$tournament)

library(arrow)
results <- read_parquet("results.parquet")
results[, c("tournament", "players.p1.name", "players.p2.name", "winner")]

# Lists are stored as JSON text.
library(jsonlite)
sets <- lapply(results$score.sets, function(x) if (is.na(x)) NULL else fromJSON(x))"""

EXPORT_PYTHON = """from livetennisapi_export import export, fetch, to_dataframe, write

rows = fetch("fixtures", tour="atp")               # a list of dicts
write(rows, "fixtures.jsonl")

export("matches", "results.csv", status="completed", from_="2026-11-01", to="2026-11-07")

df = to_dataframe(fetch("rankings", system="atp"))  # the same flat columns as the CSV"""


def _export_drift(spec: dict[str, Any]) -> None:
    """Fail the build when the page names an endpoint or a page size the spec no longer has."""
    problems = []
    for name, path, *_ in EXPORT_DATASETS:
        if "get" not in spec["paths"].get(path, {}):
            problems.append(f"dataset {name} reads GET {path}, which the spec does not define")
    limit = spec["components"]["parameters"]["limit"]["schema"].get("maximum")
    if limit != EXPORT_PAGE_SIZE:
        problems.append(f"the page says pages hold {EXPORT_PAGE_SIZE} rows, the spec's limit maximum is {limit}")
    schemas = spec["components"]["schemas"]

    def props(node: Any) -> dict[str, Any]:
        node = resolve(node, spec)
        found: dict[str, Any] = {}
        for key in ("allOf", "anyOf", "oneOf"):
            for sub in node.get(key, []):
                found.update(props(sub))
        found.update(node.get("properties", {}))
        return found

    for _what, schema, columns in EXPORT_SEEN:
        for column in columns:
            node: Any = schemas[schema]
            for part in column.split("."):
                fields = props(node)
                if part not in fields:
                    problems.append(f"column {column} is not a field of the spec's {schema} schema")
                    break
                node = fields[part]
    if problems:
        raise SystemExit("export-formats.html disagrees with the spec:\n  " + "\n  ".join(problems))


def _export_body(spec: dict[str, Any]) -> str:
    _export_drift(spec)
    format_table = scrollx(
        f"<table>{vh_caption('The three export formats and when each fits')}"
        '<thead><tr><th scope="col">Format</th><th scope="col">File name</th>'
        '<th scope="col">What a row is</th><th scope="col">Pick it when</th></tr></thead><tbody>'
        + "".join(f'<tr><td>{name}</td><td style="white-space:nowrap">{ext}</td><td>{shape}</td><td>{fits}</td></tr>\n'
                  for name, ext, shape, fits in EXPORT_FORMATS)
        + "</tbody></table>",
        "Export formats",
    )
    dataset_table = scrollx(
        f"<table>{vh_caption('The six datasets, the endpoint each reads and the plan it needs')}"
        '<thead><tr><th scope="col">Dataset</th><th scope="col">Endpoint</th>'
        '<th scope="col">Plan</th><th scope="col">Requests</th></tr></thead><tbody>'
        # The dataset name is one short word. Without nowrap the page's overflow-wrap splits it.
        + "".join(f'<tr><td style="white-space:nowrap"><code>{E(name)}</code></td><td><code>{E(shown)}</code></td>'
                  f"<td>{plan}</td><td>{requests}</td></tr>\n"
                  for name, _path, shown, plan, requests in EXPORT_DATASETS)
        + "</tbody></table>",
        "Datasets",
    )
    flat_table = scrollx(
        f"<table>{vh_caption('The columns the example row becomes')}"
        '<thead><tr><th scope="col">Column</th><th scope="col">Value in the CSV</th></tr></thead><tbody>'
        + "".join(f"<tr><td><code>{E(col)}</code></td><td><code>{E(val)}</code></td></tr>\n"
                  for col, val in EXPORT_FLAT)
        + "</tbody></table>",
        "Flattened columns",
    )
    seen_table = scrollx(
        f"<table>{vh_caption('Some of the column names in each export')}"
        '<thead><tr><th scope="col">Export</th><th scope="col">Some of its columns</th></tr></thead><tbody>'
        + "".join(f"<tr><td>{what}</td><td>{', '.join(f'<code>{E(c)}</code>' for c in cols)}</td></tr>\n"
                  for what, _schema, cols in EXPORT_SEEN)
        + "</tbody></table>",
        "Column names",
    )
    return f"""<h2 id="install">Install livetennisapi-export</h2>
<p>The package is <a href="{EXPORT_PYPI}">{EXPORT_PACKAGE}</a> on PyPI. It needs Python 3.9 or later
and installs the official Python client with it.</p>
<pre><code>pip install livetennisapi-export
pip install "livetennisapi-export[parquet]"</code></pre>
<p>The second line adds Parquet support. The <code>parquet</code> extra brings in pandas and pyarrow.</p>

<h2 id="api-key">Set the API key</h2>
<p>The command reads your key from the <code>LIVETENNISAPI_KEY</code> environment variable.
<a href="{SITE}/subscribe/free">Get a free key</a>.</p>
<pre><code>export LIVETENNISAPI_KEY=twjp_...</code></pre>
<p>There is no flag for the key, so the key is never part of the export command. Without the variable the
command prints where to get a key and exits with status 2. It sends no request.</p>

<h2 id="formats">Which format should I pick?</h2>
<p>The file name picks the format. All three hold the same rows.</p>
{format_table}
<p>CSV is the one every tool opens. A reader has to work out the types again, because a CSV cell is text.
JSON Lines is the only format that keeps nested objects as objects. Parquet keeps a type for
each column, so a rank stays a number and a flag stays a boolean.</p>
<p>Use <code>-o -</code> with <code>-f csv</code> or <code>-f jsonl</code> to write to stdout.
Parquet is binary and needs a file name.</p>

<h2 id="datasets">Which datasets can I export, and which plan does each need?</h2>
<p>There are six datasets. Each one reads a single endpoint through the official Python client.
The plans are the ones the package states.</p>
{dataset_table}
<p>If your plan does not cover a request, the API answers 403. The command then prints the refusal
and exits with status 1. Plans and prices are on the <a href="{SITE}/pricing">pricing page</a>.
The <a href="./errors-and-rate-limits.html">errors page</a> explains each status.</p>
<p>The spec also gives a FREE key 20 history calls each calendar month, which <code>completed</code>
matches can use.</p>
<p><code>rankings</code> exports one ranking table in rank order, so it needs <code>--system</code>.
The choices are <code>atp</code>, <code>wta</code>, <code>itf_jt</code>, <code>itf_mt</code>,
<code>itf_wt</code>, <code>elo</code>, <code>atp_doubles</code> and <code>wta_doubles</code>.
<code>elo</code> also needs <code>--tour atp</code> or <code>--tour wta</code>.
<code>matches</code> takes <code>--status</code>, and it defaults to <code>upcoming</code>.</p>
<pre><code>{E(EXPORT_COMMANDS)}</code></pre>
<p><code>livetennisapi-export DATASET --help</code> lists every option for a dataset.</p>

<h2 id="paging">How does paging work?</h2>
<p>The command asks for pages of {EXPORT_PAGE_SIZE} rows, the largest page the API allows. It moves
the offset forward by the rows it received and stops when <code>meta.has_more</code> is false.
You never page by hand.</p>
<ul>
<li>Each page is one request against your quota. <code>--max-rows N</code> stops after N rows and
sends no further request.</li>
<li><code>--page-size</code> takes 1 to {EXPORT_PAGE_SIZE}. Smaller pages mean more requests for the same rows.</li>
<li><code>player</code> is not paged. It sends one request for each player id you list.</li>
</ul>
<p>Quotas for each plan are on the
<a href="./auth-quota-and-health.html">authentication, quota and status</a> page.</p>

<h2 id="columns">How do nested fields become columns?</h2>
<p>JSON Lines needs no change, so each line is the object the API returned. CSV and Parquet need flat
columns. The writer applies the same rules to both.</p>
<ul>
<li>A nested object becomes one column for each field, named with dots.</li>
<li>A list becomes JSON text in one column.</li>
<li>An empty value is an empty cell in CSV and a null in Parquet.</li>
<li>A boolean is <code>true</code> or <code>false</code> in CSV.</li>
</ul>
<p>Here is a match row cut down to a few fields. The values are made up.</p>
<pre><code>{E(EXPORT_NESTED)}</code></pre>
<p>It becomes six columns.</p>
{flat_table}
<p>The columns follow the fields the API sent, in the order they first appear. A field added to the
API shows up as a new column with no upgrade. These are some of the columns each export has.
Every name is a field the <a href="./reference.html">reference</a> documents.</p>
{seen_table}
<p>A match file is wide, because each player object and the score object spread into their own
columns. In Parquet a whole-number column that has an empty value is stored as a decimal number.</p>

<h2 id="writes">When is the file written?</h2>
<p>Nothing is written until every page has arrived. A request that fails halfway leaves no
half-written file. A file of the same name from an earlier run stays as it was.</p>
<ul>
<li>A refused API key writes no file. The command prints the refusal and exits with status 1.</li>
<li>A missing key, an unknown file extension with no <code>-f</code> and Parquet to stdout are caught before any
request is sent.
The command exits with status 2.</li>
<li>On success the command exits with status 0. When it writes a file, it prints the row count and the
file name to stderr.</li>
<li>A request that matches no rows still writes the file. The CSV is then empty, with no header line.</li>
</ul>

<h2 id="pandas">How do I read an export in pandas?</h2>
<p>A dotted name is an ordinary column label in pandas.</p>
<pre><code>{E(EXPORT_PANDAS)}</code></pre>

<h2 id="duckdb">How do I query an export in DuckDB?</h2>
<p>DuckDB reads all three formats from the file name.</p>
<pre><code>{E(EXPORT_DUCKDB)}</code></pre>

<h2 id="r">How do I read an export in R?</h2>
<p>Base R reads the CSV. The <code>arrow</code> package reads the Parquet file.</p>
<pre><code>{E(EXPORT_R)}</code></pre>

<h2 id="python">Can I export from Python code?</h2>
<p>The same package is a small Python API. <code>fetch</code> returns the rows, <code>write</code>
writes them and <code>export</code> does both.</p>
<pre><code>{E(EXPORT_PYTHON)}</code></pre>
<p><code>from_</code> is the <code>from</code> parameter, renamed because <code>from</code> is a Python keyword.
<code>fetch</code> and <code>export</code> take <code>api_key=</code> or read <code>LIVETENNISAPI_KEY</code>.
<code>to_dataframe</code> needs the <code>parquet</code> extra.</p>

<h2 id="links">Links</h2>
<ul>
<li><a href="{EXPORT_PYPI}">livetennisapi-export on PyPI</a></li>
<li><a href="{EXPORT_REPO}">Source on GitHub</a></li>
<li><a href="{SITE}/subscribe/free">Free API key</a></li>
<li><a href="./live-scores.html">Live scores</a>, the <code>/matches</code> endpoint</li>
<li><a href="./players-and-tournaments.html">Players, tournaments and rankings</a></li>
</ul>
"""


# ----------------------------------------------------------------- client libraries -------------
# Every cell on the client libraries page was read from a real source on CLIENTS_CHECKED.
# Versions, licences and minimum runtimes come from the registry that publishes each package
# (PyPI, npm, the Go module proxy, Packagist, NuGet, pub.dev, R-universe). The Swift client has
# no registry, so its version is the newest Git tag. Coverage (the stream column and
# CLIENT_ENDPOINT_GROUPS) was read from the source of each published version, not from the main
# branch. Each quick-start snippet is copied from the README of that published version.
# scripts/check_client_versions.py reads the registries again and fails when a row is behind.
# After a release, update the row here, re-read its coverage and run that script.
CLIENTS_CHECKED = "2026-11-12"
CLIENTS_ORG = "https://github.com/livetennisapi"

# One row per library. `source` is (registry kind, identifier) for check_client_versions.py.
# `runtime_spec` is the registry's own minimum-runtime field, held next to the wording the page
# shows so the check script can compare it. `stream`, `export` and `mcp` are the cell texts.
CLIENTS: list[dict[str, Any]] = [
    {"key": "python", "name": "Python client", "language": "Python", "package": "livetennisapi",
     "registry": "PyPI", "registry_url": PYPI_URL, "source": ("pypi", "livetennisapi"),
     "install": "pip install livetennisapi", "version": "1.8.0",
     "runtime": "Python 3.9", "runtime_spec": ">=3.9",
     "stream": "Yes", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-python"},
    {"key": "js", "name": "JavaScript and TypeScript client", "language": "JavaScript, TypeScript",
     "package": "livetennisapi", "registry": "npm", "registry_url": NPM_JS_URL,
     "source": ("npm", "livetennisapi"),
     "install": "npm install livetennisapi", "version": "1.10.2",
     "runtime": "Node 18", "runtime_spec": ">=18",
     "stream": "Yes", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-js"},
    {"key": "go", "name": "Go client", "language": "Go",
     "package": "github.com/livetennisapi/livetennisapi-go", "registry": "Go modules",
     "registry_url": "https://pkg.go.dev/github.com/livetennisapi/livetennisapi-go",
     "source": ("go", "github.com/livetennisapi/livetennisapi-go"),
     "install": "go get github.com/livetennisapi/livetennisapi-go", "version": "1.2.1",
     "runtime": "Go 1.25", "runtime_spec": "1.25",
     "stream": "Token only", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-go"},
    {"key": "php", "name": "PHP client", "language": "PHP", "package": "livetennisapi/livetennisapi",
     "registry": "Packagist", "registry_url": "https://packagist.org/packages/livetennisapi/livetennisapi",
     "source": ("packagist", "livetennisapi/livetennisapi"),
     "install": "composer require livetennisapi/livetennisapi", "version": "1.1.1",
     "runtime": "PHP 8.1", "runtime_spec": ">=8.1",
     "stream": "Token only", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-php"},
    {"key": "dotnet", "name": ".NET client", "language": "C#", "package": "LiveTennisApi",
     "registry": "NuGet", "registry_url": "https://www.nuget.org/packages/LiveTennisApi",
     "source": ("nuget", "livetennisapi"),
     "install": "dotnet add package LiveTennisApi", "version": "1.2.1",
     "runtime": ".NET Standard 2.0 or .NET 8", "runtime_spec": ".NETStandard2.0, net8.0",
     "stream": "Token only", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-dotnet"},
    {"key": "dart", "name": "Dart and Flutter client", "language": "Dart", "package": "livetennisapi",
     "registry": "pub.dev", "registry_url": "https://pub.dev/packages/livetennisapi",
     "source": ("pub", "livetennisapi"),
     "install": "dart pub add livetennisapi", "version": "1.2.1",
     "runtime": "Dart 3.5", "runtime_spec": "^3.5.0",
     "stream": "Token only", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-dart"},
    {"key": "swift", "name": "Swift client", "language": "Swift", "package": "livetennisapi-swift",
     "registry": "Git tag", "registry_url": f"{CLIENTS_ORG}/livetennisapi-swift/tags",
     "source": ("github-tag", "livetennisapi/livetennisapi-swift"),
     "install": '.package(url: "https://github.com/livetennisapi/livetennisapi-swift.git", from: "1.1.1")',
     "version": "1.1.1", "runtime": "Swift 5.9", "runtime_spec": "5.9",
     "stream": "Token only", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-swift"},
    {"key": "r", "name": "R client", "language": "R", "package": "livetennisapi",
     "registry": "R-universe", "registry_url": "https://livetennisapi.r-universe.dev/livetennisapi",
     "source": ("r-universe", "livetennisapi/livetennisapi"),
     "install": 'install.packages("livetennisapi", repos = c("https://livetennisapi.r-universe.dev", '
                '"https://cloud.r-project.org"))',
     "version": "0.2.0", "runtime": "R 4.1", "runtime_spec": ">= 4.1",
     "stream": "No", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-r"},
    {"key": "mcp", "name": "MCP server", "language": "TypeScript", "package": "livetennisapi-mcp",
     "registry": "npm", "registry_url": NPM_MCP_URL, "source": ("npm", "livetennisapi-mcp"),
     "install": "npx -y livetennisapi-mcp", "version": "1.6.5",
     "runtime": "Node 20", "runtime_spec": ">=20",
     "stream": "No", "export": "No", "mcp": "Yes", "repo": f"{CLIENTS_ORG}/livetennisapi-mcp"},
    {"key": "ai", "name": "Vercel AI SDK tools", "language": "TypeScript", "package": AI_SDK_PACKAGE,
     "registry": "npm", "registry_url": AI_SDK_NPM, "source": ("npm", AI_SDK_PACKAGE),
     "install": "npm install livetennisapi-ai", "version": AI_SDK_VERSION,
     "runtime": "Node 22", "runtime_spec": ">=22",
     "stream": "No", "export": "No", "mcp": "No", "repo": AI_SDK_REPO},
    {"key": "export", "name": "Export command", "language": "Python", "package": EXPORT_PACKAGE,
     "registry": "PyPI", "registry_url": EXPORT_PYPI, "source": ("pypi", EXPORT_PACKAGE),
     "install": "pip install livetennisapi-export", "version": EXPORT_VERSION,
     "runtime": "Python 3.9", "runtime_spec": ">=3.9",
     "stream": "No", "export": "CSV, JSON Lines, Parquet", "mcp": "No", "repo": EXPORT_REPO},
    {"key": "laravel", "name": "Laravel package", "language": "PHP",
     "package": "livetennisapi/livetennisapi-laravel", "registry": "Packagist",
     "registry_url": "https://packagist.org/packages/livetennisapi/livetennisapi-laravel",
     "source": ("packagist", "livetennisapi/livetennisapi-laravel"),
     "install": "composer require livetennisapi/livetennisapi-laravel", "version": "1.1.0",
     "runtime": "PHP 8.2", "runtime_spec": ">=8.2",
     "stream": "Token only", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-laravel"},
    {"key": "haystack", "name": "Haystack integration", "language": "Python",
     "package": "livetennisapi-haystack", "registry": "PyPI",
     "registry_url": "https://pypi.org/project/livetennisapi-haystack/",
     "source": ("pypi", "livetennisapi-haystack"),
     "install": "pip install livetennisapi-haystack", "version": "0.2.0",
     "runtime": "Python 3.10", "runtime_spec": ">=3.10",
     "stream": "No", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/livetennisapi-haystack"},
    {"key": "langchain", "name": "LangChain integration", "language": "Python",
     "package": "langchain-livetennis", "registry": "PyPI",
     "registry_url": "https://pypi.org/project/langchain-livetennis/",
     "source": ("pypi", "langchain-livetennis"),
     "install": "pip install -U langchain-livetennis", "version": "0.2.0",
     "runtime": "Python 3.10", "runtime_spec": "<4.0.0,>=3.10.0",
     "stream": "No", "export": "No", "mcp": "No", "repo": f"{CLIENTS_ORG}/langchain-livetennis"},
    {"key": "llamaindex", "name": "LlamaIndex tools", "language": "Python",
     "package": "llama-index-tools-livetennisapi", "registry": "PyPI",
     "registry_url": "https://pypi.org/project/llama-index-tools-livetennisapi/",
     "source": ("pypi", "llama-index-tools-livetennisapi"),
     "install": "pip install llama-index-tools-livetennisapi", "version": "0.1.0",
     "runtime": "Python 3.10", "runtime_spec": "<4.0,>=3.10",
     "stream": "No", "export": "No", "mcp": "No",
     "repo": f"{CLIENTS_ORG}/llama-index-tools-livetennisapi"},
]
# The rows llms.txt lists from this table. The other five have their own hand-written lines there.
CLIENTS_LLMS_EXTRA = ("go", "php", "dotnet", "dart", "swift", "r", "laravel", "haystack", "langchain",
                      "llamaindex")
# Every listed package states the MIT licence on its registry or, for Swift, in its LICENSE file.
CLIENTS_LICENCE = "MIT"

# The eight language clients, in the column order of the endpoint table.
CLIENT_LANGUAGES = ["python", "js", "go", "php", "dotnet", "dart", "swift", "r"]
CLIENT_SHORT = {"python": "Python", "js": '<abbr title="JavaScript and TypeScript">JS</abbr>', "go": "Go", "php": "PHP", "dotnet": ".NET",
                "dart": "Dart", "swift": "Swift", "r": "R"}

# (group, the spec operations it stands for, one cell per CLIENT_LANGUAGES entry).
# Y: the client has a method for every operation in the group. P: for some. N: for none.
# _clients_drift fails the build when an operation here is no longer in the spec.
CLIENT_ENDPOINT_GROUPS: list[tuple[str, list[tuple[str, str]], str]] = [
    ("Matches and live scores",
     [("get", "/matches"), ("get", "/matches/{matchId}"), ("get", "/matches/{matchId}/score")], "YYYYYYYY"),
    ("Players, fixtures and tournaments",
     [("get", "/players"), ("get", "/players/{playerId}"), ("get", "/fixtures"),
      ("get", "/tournaments"), ("get", "/tournaments/{tournamentId}")], "YYYYYYYY"),
    ("Player record", [("get", "/players/{playerId}/stats")], "NYNNNNNY"),
    ("Rankings", [("get", "/rankings")], "YYYYYYYY"),
    ("Results archive and head-to-head",
     [("get", "/history/archive/matches"), ("get", "/history/archive/matches/{archiveId}"),
      ("get", "/history/archive/players"), ("get", "/history/archive/career"), ("get", "/h2h")], "YYYYYYYP"),
    ("Completed matches and the point-by-point tape",
     [("get", "/history/matches"), ("get", "/history/matches/{matchId}")], "YYYYYYYN"),
    ("History coverage report", [("get", "/history/coverage")], "YYNNNNNN"),
    ("Match events, statistics and analysis",
     [("get", "/matches/{matchId}/events"), ("get", "/matches/{matchId}/statistics"),
      ("get", "/matches/{matchId}/analysis")], "YYYYYYYN"),
    ("Per-point events over REST", [("get", "/matches/{matchId}/points")], "YYNNNNNN"),
    ("Markets and prices", [("get", "/markets"), ("get", "/markets/{matchId}/prices")], "YYYYYYYN"),
    ("Rally and charting data",
     [("get", "/rally/matches"), ("get", "/rally/matches/{rallyMatchId}"),
      ("get", "/history/matches/{matchId}/rally"), ("get", "/charting/players"),
      ("get", "/charting/matches/{chartingMatchId}")], "YYYYYYYN"),
    ("History packages",
     [("get", "/history/packages"), ("get", "/history/packages/{period}")], "YYYYYYYN"),
    ("Webhooks",
     [("post", "/webhooks"), ("get", "/webhooks"), ("delete", "/webhooks/{webhookId}")], "NNYYYYYN"),
    ("Push feed token", [("get", "/ws-token")], "YYYYYYYN"),
    ("Usage and quota", [("get", "/usage")], "YNYYYYYY"),
]
CLIENT_CELL = {"Y": "Yes", "P": "Part", "N": "No"}

# The quick-start block of each README, unchanged. Python 1.8.0, JavaScript 1.10.2, Go 1.2.1,
# PHP 1.1.1, .NET 1.2.1, Dart 1.2.1, Swift 1.1.1 and R 0.2.0.
CLIENT_SNIPPET_PYTHON = r"""from livetennisapi import LiveTennisAPI

with LiveTennisAPI(api_key="twjp_…") as client:   # or set LIVETENNISAPI_KEY
    for match in client.list_matches(status="live"):
        print(match.tournament, match.p1.name, "vs", match.p2.name, match.score.sets)"""

CLIENT_SNIPPET_JS = r"""import { LiveTennisAPI } from 'livetennisapi';

const client = new LiveTennisAPI({ apiKey: 'twjp_…' });   // or $LIVETENNISAPI_KEY

const { data } = await client.listMatches({ status: 'live' });
for (const match of data) {
  console.log(match.tournament, match.players?.p1?.name, 'vs', match.players?.p2?.name);
}"""

CLIENT_SNIPPET_GO = r"""package main

import (
	"context"
	"fmt"
	"log"
	"os"

	"github.com/livetennisapi/livetennisapi-go"
)

func main() {
	client := livetennisapi.New(os.Getenv("LIVETENNISAPI_KEY"))

	page, err := client.ListMatches(context.Background(), livetennisapi.ListMatchesParams{
		Status:     livetennisapi.StatusLive,
		ListParams: livetennisapi.ListParams{Limit: 10},
	})
	if err != nil {
		log.Fatal(err)
	}

	for _, match := range page.Data {
		fmt.Printf("%-28s %s vs %s — %s\n",
			match.Tournament,
			match.Players.P1.Name,
			match.Players.P2.Name,
			match.Score, // nil-safe: prints "-" before a match starts
		)
	}
}"""

CLIENT_SNIPPET_PHP = r"""use LiveTennisApi\LiveTennisApi;

$client = new LiveTennisApi('twjp_…');      // or set LIVETENNISAPI_KEY

foreach ($client->listMatches('live') as $match) {
    echo $match->tournament, ' [', $match->tour, ']: ',
         $match->p1()?->name, ' vs ', $match->p2()?->name, "\n";

    // score is nullable — an upcoming match has none yet
    if ($match->score !== null) {
        // points are STRINGS ("40", "AD"); games are player-major per-set lists
        echo '  ', implode('-', $match->score->points), "\n";
    }
}"""

CLIENT_SNIPPET_DOTNET = r"""using LiveTennisApi;
using LiveTennisApi.Models;

using var client = new LiveTennisApiClient("twjp_your_key");

var live = await client.ListMatchesAsync(MatchStatus.Live);
foreach (var m in live.Data)
{
    Console.WriteLine($"{m.Tournament}: {m.Players?.P1?.Name} vs {m.Players?.P2?.Name}");
}"""

CLIENT_SNIPPET_DART = r"""import 'package:livetennisapi/livetennisapi.dart';

Future<void> main() async {
  final client = LiveTennisApi(apiKey: 'twjp_your_key');
  try {
    final page = await client.listMatches(status: MatchStatus.live);
    for (final match in page.data) {
      final s = match.score;
      final (g1, g2) = s?.gamesForSet(0) ?? (null, null);
      print('${match.tournament} [${match.tour}]: '
          '${match.p1?.name} vs ${match.p2?.name} '
          '(${g1 ?? '-'}-${g2 ?? '-'}, serving: ${s?.server ?? '—'})');
    }
  } on UpgradeRequiredException catch (e) {
    print('Needs the ${e.requiredTier} tier');
  } on RateLimitedException catch (e) {
    print('Slow down; retry after ${e.retryAfter}s');
  } finally {
    client.close();
  }
}"""

CLIENT_SNIPPET_SWIFT = r"""import LiveTennisApi

let client = LiveTennisApiClient(apiKey: "twjp_your_key_here")

let live = try await client.listMatches(status: .live, tour: .atp)
for match in live.data {
    let p1 = match.players?.p1?.name ?? "?"
    let p2 = match.players?.p2?.name ?? "?"
    print("\(match.tournament): \(p1) vs \(p2) — \(match.score?.description ?? "-")")
}"""

CLIENT_SNIPPET_R = r"""library(livetennisapi)

live <- live_matches(tour = "atp")
if (nrow(live) > 0) {
  print(live[, c("id", "tournament", "players.p1.name", "players.p2.name")])
  match_score(live$id[1])
}

search_players("sinner")
list_fixtures(tour = "wta", limit = 20)"""

# (client key, heading, install lines, snippet, a note the README or the registry supports).
CLIENT_QUICKSTARTS = [
    ("python", "Python", "pip install livetennisapi", CLIENT_SNIPPET_PYTHON,
     "The client reads <code>LIVETENNISAPI_KEY</code> when you pass no key."),
    ("js", "JavaScript and TypeScript", "npm install livetennisapi", CLIENT_SNIPPET_JS,
     "The package has no runtime dependencies and ships its own types."),
    ("go", "Go", "go get github.com/livetennisapi/livetennisapi-go", CLIENT_SNIPPET_GO,
     "The module uses the standard library only."),
    ("php", "PHP", "composer require livetennisapi/livetennisapi\ncomposer require guzzlehttp/guzzle",
     CLIENT_SNIPPET_PHP,
     "The client needs a PSR-18 HTTP client and PSR-17 factories. The second line installs Guzzle, "
     "which provides both."),
    ("dotnet", ".NET", "dotnet add package LiveTennisApi", CLIENT_SNIPPET_DOTNET,
     "The package targets .NET Standard 2.0 and .NET 8."),
    ("dart", "Dart and Flutter", "dart pub add livetennisapi", CLIENT_SNIPPET_DART,
     "The package is pure Dart and depends only on <code>package:http</code>."),
    ("swift", "Swift",
     '.package(url: "https://github.com/livetennisapi/livetennisapi-swift.git", from: "1.1.1")',
     CLIENT_SNIPPET_SWIFT,
     "Add the first line to the dependencies in <code>Package.swift</code>. The package supports "
     "macOS 12, iOS 15, tvOS 15, watchOS 8 and Linux."),
    ("r", "R",
     'install.packages("livetennisapi", repos = c("https://livetennisapi.r-universe.dev", '
     '"https://cloud.r-project.org"))',
     CLIENT_SNIPPET_R,
     "List functions return a tibble. Put the key in <code>~/.Renviron</code> as "
     "<code>LIVETENNISAPI_KEY</code>."),
]


def _clients_drift(spec: dict[str, Any]) -> None:
    """Fail the build when the page names an operation the spec no longer has, or a row is malformed."""
    problems = []
    for group, operations, cells in CLIENT_ENDPOINT_GROUPS:
        for method, path in operations:
            if method not in spec["paths"].get(path, {}):
                problems.append(f"group {group!r} names {method.upper()} {path}, which the spec does not define")
        if len(cells) != len(CLIENT_LANGUAGES) or set(cells) - set(CLIENT_CELL):
            problems.append(f"group {group!r} needs one of Y, P or N for each of {len(CLIENT_LANGUAGES)} clients")
    keys = [c["key"] for c in CLIENTS]
    if len(set(keys)) != len(keys):
        problems.append("two rows share a key")
    for key in CLIENT_LANGUAGES + [q[0] for q in CLIENT_QUICKSTARTS]:
        if key not in keys:
            problems.append(f"no row for the client {key!r}")
    by_key = {c["key"]: c for c in CLIENTS}
    for key, _heading, install, _snippet, _note in CLIENT_QUICKSTARTS:
        if key in by_key and by_key[key]["install"] not in install:
            problems.append(f"the {key} quick start does not use the install command in its row")
    # The prose states these counts and names. A changed row must change the sentence too.
    if len(CLIENT_LANGUAGES) != 8 or len(CLIENTS) - len(CLIENT_LANGUAGES) != 7:
        problems.append("the lede and the title say eight language clients and seven more packages")
    if [c["key"] for c in CLIENTS if c["stream"] == "Yes"] != ["python", "js"]:
        problems.append("the page says the Python and JavaScript clients open the live stream, and only they")
    if [c["key"] for c in CLIENTS if c["export"] != "No"] != ["export"]:
        problems.append("the page says one package writes files")
    if [c["key"] for c in CLIENTS if c["mcp"] == "Yes"] != ["mcp"]:
        problems.append("the page says one package is an MCP server")
    part = [(group, CLIENT_LANGUAGES[i]) for group, _ops, cells in CLIENT_ENDPOINT_GROUPS
            for i, cell in enumerate(cells) if cell == "P"]
    if part != [("Results archive and head-to-head", "r")]:
        problems.append("the page explains Part for the R client's archive row only")
    swift = by_key.get("swift")
    if swift and f'from: "{swift["version"]}"' not in swift["install"]:
        problems.append("the Swift install line does not name the Swift row's version")
    if "get" not in spec["paths"].get("/ws-token", {}):
        problems.append("the page explains Token only with GET /ws-token, which the spec does not define")
    if problems:
        raise SystemExit("client-libraries.html disagrees with the spec or itself:\n  " + "\n  ".join(problems))


def _clients_body(spec: dict[str, Any]) -> str:
    _clients_drift(spec)
    by_key = {c["key"]: c for c in CLIENTS}

    # The page's overflow-wrap splits a short word mid-letter in a narrow column. These cells
    # wrap at spaces only, and a short command or a package name stays on one line.
    words = ' style="overflow-wrap:normal"'
    nowrap = ' style="white-space:nowrap"'

    def install_cell(c: dict[str, Any]) -> str:
        style = nowrap if len(c["install"]) <= 52 else ""
        return (f'<td><span{style}><code>{E(c["install"])}</code></span><br>'
                f'<span{nowrap}><a href="{c["registry_url"]}">{E(c["package"])}</a> on {E(c["registry"])}</span></td>')

    rows = "".join(
        # Version and runtime sit next to the name, so a phone shows all three before any scrolling.
        f'<tr><td{nowrap}>{E(c["name"])}</td><td>{E(c["version"])}</td><td{words}>{E(c["runtime"])}</td>'
        + install_cell(c)
        + f'<td{words}>{E(c["language"])}</td>'
        f'<td>{CLIENTS_LICENCE}</td><td><a href="{c["repo"]}">GitHub</a></td></tr>\n'
        for c in CLIENTS
    )
    matrix = scrollx(
        f"<table>{vh_caption('Every official client library and tool, with its install command and version')}"
        '<thead><tr><th scope="col">Library</th><th scope="col">Latest version</th>'
        '<th scope="col">Minimum runtime</th><th scope="col">Install and package</th>'
        '<th scope="col">Language</th><th scope="col">Licence</th><th scope="col">Source</th>'
        "</tr></thead><tbody>" + rows + "</tbody></table>",
        "Client libraries",
    )
    cover_rows = "".join(
        f'<tr><td{nowrap}>{E(c["name"])}</td><td>Yes</td><td{nowrap}>{E(c["stream"])}</td>'
        f'<td{words}>{E(c["export"])}</td><td>{E(c["mcp"])}</td></tr>\n'
        for c in CLIENTS
    )
    coverage = scrollx(
        f"<table>{vh_caption('Which parts of the API each library covers')}"
        '<thead><tr><th scope="col">Library</th><th scope="col">REST</th><th scope="col">Live stream</th>'
        '<th scope="col">File export</th><th scope="col">MCP</th></tr></thead><tbody>'
        + cover_rows + "</tbody></table>",
        "API coverage",
    )
    group_rows = "".join(
        f"<tr><td{words}>{E(group)}</td>"
        + "".join(f"<td{nowrap}>{CLIENT_CELL[cell]}</td>" for cell in cells)
        # One path to a line, each unbroken: in a narrow column the page's overflow-wrap cuts a path
        # into four-letter pieces. Paths come last so a phone shows the first clients beside the name.
        + f"<td{nowrap}>"
        + "<br>".join(f"<code>{E((m.upper() + ' ' if m != 'get' else '') + p)}</code>" for m, p in operations)
        + "</td></tr>\n"
        for group, operations, cells in CLIENT_ENDPOINT_GROUPS
    )
    groups = scrollx(
        f"<table>{vh_caption('Endpoint groups and the language clients that cover them')}"
        '<thead><tr><th scope="col">Endpoints</th>'
        + "".join(f'<th scope="col">{CLIENT_SHORT[k]}</th>' for k in CLIENT_LANGUAGES)
        + '<th scope="col">Paths</th></tr></thead><tbody>' + group_rows + "</tbody></table>",
        "Endpoint coverage",
    )
    quickstarts = "".join(
        f'<h3 id="{key}">{E(heading)}</h3>\n'
        f"<pre><code>{E(install)}</code></pre>\n"
        # The Go README indents with tabs. At the default width of 8 a phone wraps every line.
        f'<pre style="tab-size:4"><code>{E(snippet)}</code></pre>\n'
        f'<p>{note} The example is from the <a href="{by_key[key]["repo"]}#readme">README</a> of '
        f'version {E(by_key[key]["version"])}.</p>\n'
        for key, heading, install, snippet, note in CLIENT_QUICKSTARTS
    )
    return f"""<h2 id="matrix">Which client library should I use?</h2>
<p>Pick the row for your language. Every package calls the same REST API with the same key.
The version is the newest release on the registry named under each install command.
These client libraries are the official SDKs for the API.</p>
{matrix}
<p>Every package is MIT licensed. Plugins for apps and automation platforms are not in this table.
They live in the <a href="{CLIENTS_ORG}">GitHub organisation</a>.</p>

<h2 id="coverage">Which libraries support REST, the live stream, file export and MCP?</h2>
<p>Every library reads the REST API. Two open the live stream, one writes files and one is an MCP server.</p>
{coverage}
<p><strong>Live stream</strong> says whether the package opens the WebSocket feed for you. The Python and
JavaScript clients do. In Python, <code>pip install "livetennisapi[all]"</code> adds the WebSocket feed.</p>
<p><strong>Token only</strong> means the client calls <code>GET /ws-token</code> for a push feed token.
You open the socket with your own WebSocket library. The
<a href="./push-feed-and-webhooks.html">push feed and webhooks page</a> describes the frames.</p>
<p>The MCP server also runs hosted at <code>https://mcp.livetennisapi.com/mcp</code>, with nothing to install.
The <a href="./ai-sdk.html">AI SDK guide</a> and the <a href="./export-formats.html">export guide</a>
cover those two packages in full.</p>
<h2 id="endpoints">Which endpoints does each client cover?</h2>
<p>The eight language clients do not all reach the same endpoints. Each cell was read from the source
of the published version in the first table.</p>
{groups}
<p><strong>Part</strong> for R means it lists archive results, players, careers and head-to-head records.
It has no call for a single archive result.</p>
<p>An endpoint with no method in your client is still one HTTP request away. The
<a href="./reference.html">reference</a> lists every path. The
<a href="./errors-and-rate-limits.html">errors page</a> says when to retry.</p>

<h2 id="quickstart">What is the smallest working call in each language?</h2>
<p>Each example lists live matches. Every call needs an API key, and
<a href="{SITE}/subscribe/free">a free key</a> is enough for these. The free plan has 100 requests a day.</p>
{quickstarts}
<h2 id="versions">How do I check that a version here is current?</h2>
<p>The versions were read from the registries on
<time datetime="{CLIENTS_CHECKED}">{CLIENTS_CHECKED}</time>. The registry link under each
install command always shows the newest release.</p>
<p>The docs repository has a script, <code>scripts/check_client_versions.py</code>. It reads every
registry again and names each row that is behind.</p>

<h2 id="links">Links</h2>
<ul>
<li><a href="{CLIENTS_ORG}">Every repository in the GitHub organisation</a></li>
<li><a href="./openapi.yaml">The OpenAPI spec</a>, for generating a client in another language</li>
<li><a href="{SITE}/subscribe/free">Free API key</a></li>
<li><a href="./auth-quota-and-health.html">Authentication, quota and status</a></li>
</ul>
"""


GUIDES: list[dict[str, Any]] = [
    {
        "slug": "ai-sdk",
        "title": "Live Tennis API tools for the Vercel AI SDK",
        # The h1 already says Live Tennis API, so the head title leads with the search terms
        # and keeps the brand for the end. A pipe, since the house style has no dashes.
        "head_title": "Tennis API tools for the Vercel AI SDK | Live Tennis API",
        "question": "How do you give a Vercel AI SDK model live tennis data?",
        "description": (
            "How do you give a Vercel AI SDK model live tennis data? Install livetennisapi-ai "
            "and pass livetennisTools() to generateText. Free keys need no card."
        ),
        "lede": (
            f'Install <a href="{AI_SDK_NPM}"><code>livetennisapi-ai</code></a> and pass '
            "<code>livetennisTools()</code> to <code>generateText</code>. The model gets 25 "
            "read-only tools for live scores, players, fixtures, rankings, head-to-head, the "
            "results archive and model win probability."
        ),
        "meta": (
            f'Package <a href="{AI_SDK_NPM}">livetennisapi-ai</a> {AI_SDK_VERSION}, for <code>ai</code> v7. '
            f'Tested with ai 7.0.148 on <time datetime="{AI_SDK_CHECKED}">{AI_SDK_CHECKED}</time>. '
            "Free keys need no card."
        ),
        "body": _ai_sdk_body,
        "date": AI_SDK_CHECKED,
        "about": {"@type": "SoftwareSourceCode", "name": AI_SDK_PACKAGE, "url": AI_SDK_NPM,
                  "version": AI_SDK_VERSION, "programmingLanguage": "TypeScript",
                  "runtimePlatform": "Node.js"},
        "footer": (
            f'Written for <a href="{AI_SDK_NPM}">livetennisapi-ai</a> {AI_SDK_VERSION}. Package source in '
            f'<a href="{AI_SDK_REPO}">livetennisapi/livetennisapi-ai</a>, page source in '
            '<a href="https://github.com/livetennisapi/openapi">livetennisapi/openapi</a>.'
        ),
    },
    {
        "slug": "errors-and-rate-limits",
        "title": "Errors and rate limits",
        "head_title": "Tennis API errors and rate limits | Live Tennis API",
        "question": "What does each Live Tennis API error mean, and when should a client retry?",
        "description": (
            "Every Live Tennis API error code, what causes it and what to do. Retry only a "
            "per-minute 429 or a 5xx, after the Retry-After wait."
        ),
        "lede": (
            "Every error is JSON with a stable <code>error</code> code. Retry a per-minute 429 and "
            "any 5xx, waiting <code>Retry-After</code> when it is sent. Fix the request on a 400, the "
            "key on a 401 and the plan on a 403. The daily-quota 429 and <code>abuse_throttled</code> "
            "are never retried."
        ),
        "meta": (
            "Status codes and error codes are read from the OpenAPI spec when the page is built. "
            f'Retry rules checked against livetennisapi {ERRORS_PY_VERSION} for Python and '
            f'{ERRORS_JS_VERSION} for JS on <time datetime="{ERRORS_CHECKED}">{ERRORS_CHECKED}</time>.'
        ),
        "body": _errors_body,
        "date": ERRORS_CHECKED,
        "about": {"@type": "WebAPI", "name": "Live Tennis API", "url": SITE,
                  "documentation": f"{DOCS_URL}/reference.html"},
        "footer": (
            'Built from <a href="./openapi.yaml">openapi.yaml</a>. Page source in '
            '<a href="https://github.com/livetennisapi/openapi">livetennisapi/openapi</a>.'
        ),
    },
    {
        "slug": "export-formats",
        "title": "Export tennis data to CSV, JSON Lines or Parquet",
        "head_title": "Export tennis data: CSV, JSONL or Parquet | Live Tennis API",
        "question": "How do you export tennis data to CSV, JSON Lines or Parquet?",
        "description": (
            "Export tennis matches, fixtures, players and rankings to CSV, JSON Lines or Parquet "
            "with livetennisapi-export. Read the files in pandas, DuckDB or R."
        ),
        "lede": (
            f'Install <a href="{EXPORT_PYPI}"><code>livetennisapi-export</code></a>, set '
            "<code>LIVETENNISAPI_KEY</code> and name an output file. The file extension picks the "
            "format. The command pages through every result and writes matches, fixtures, players, "
            "rankings or tournaments."
        ),
        "meta": (
            f'Package <a href="{EXPORT_PYPI}">livetennisapi-export</a> {EXPORT_VERSION}, for Python 3.9 or later. '
            f'Read-back examples run on <time datetime="{EXPORT_CHECKED}">{EXPORT_CHECKED}</time> '
            "with pandas 3.1.1, DuckDB 2.0.0 and R 4.6.2."
        ),
        "body": _export_body,
        "date": EXPORT_CHECKED,
        "about": {"@type": "SoftwareSourceCode", "name": EXPORT_PACKAGE, "url": EXPORT_PYPI,
                  "version": EXPORT_VERSION, "codeRepository": EXPORT_REPO,
                  "programmingLanguage": "Python"},
        "footer": (
            f'Written for <a href="{EXPORT_PYPI}">livetennisapi-export</a> {EXPORT_VERSION}. Package source in '
            f'<a href="{EXPORT_REPO}">livetennisapi/livetennisapi-export</a>, page source in '
            '<a href="https://github.com/livetennisapi/openapi">livetennisapi/openapi</a>.'
        ),
    },
    {
        "slug": "client-libraries",
        "title": "Live Tennis API client libraries",
        "head_title": "Tennis API client libraries and SDKs | Live Tennis API",
        "question": "Which client libraries does the Live Tennis API have?",
        "description": (
            "Official Live Tennis API client libraries for Python, JavaScript, Go, PHP, .NET, Dart, "
            "R and Swift, with install commands, versions and coverage."
        ),
        "lede": (
            "There are official clients for Python, JavaScript and TypeScript, Go, PHP, .NET, Dart, "
            "R and Swift. Seven more packages build on them, among them an MCP server and an export "
            "command. The tables list the install command, the latest version and the coverage of each."
        ),
        "meta": (
            f'Versions read from each registry on <time datetime="{CLIENTS_CHECKED}">{CLIENTS_CHECKED}</time>. '
            "Coverage read from the source of each published version."
        ),
        "body": _clients_body,
        "date": CLIENTS_CHECKED,
        "about": [
            {"@type": "SoftwareSourceCode", "name": f'Live Tennis API {c["name"]}',
             "alternateName": c["package"], "url": c["registry_url"], "version": c["version"],
             "codeRepository": c["repo"],
             "programmingLanguage": c["language"].split(", ") if ", " in c["language"] else c["language"],
             "license": "https://opensource.org/license/mit"}
            for c in CLIENTS
        ],
        "footer": (
            f"Versions and coverage checked on {CLIENTS_CHECKED}. Library source in the "
            f'<a href="{CLIENTS_ORG}">livetennisapi</a> organisation, page source in '
            '<a href="https://github.com/livetennisapi/openapi">livetennisapi/openapi</a>.'
        ),
    },
]


def build_guide_pages(spec: dict[str, Any], reference_html: str) -> dict[str, str]:
    """{slug: html} for GUIDES, in the topic pages' template."""
    style_html = reference_base_style(reference_html)
    pages = {}
    for guide in GUIDES:
        desc = guide["description"]
        if len(E(desc)) > DESC_MAX:
            raise SystemExit(f"guide {guide['slug']}: meta description over {DESC_MAX} characters")
        siblings = "\n".join(
            f'<a href="./{t["slug"]}.html">{E(t["title"])}</a>'
            for t in TOPICS + GUIDES if t["slug"] != guide["slug"]
        )
        # The page's own <header> gets role="none": the site header above is the one banner
        # landmark, and a second one makes screen-reader landmark lists ambiguous.
        ld_json = tech_article_ld(guide["title"], desc, f"{DOCS_URL}/{guide['slug']}.html",
                                  dateModified=guide["date"], about=guide["about"])
        pages[guide["slug"]] = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(guide['head_title'])}</title>
<meta name="description" content="{E(desc)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{DOCS_URL}/{guide['slug']}.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{E(guide['title'])}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{DOCS_URL}/{guide['slug']}.html">
<meta property="og:image" content="{DOCS_URL}/banner.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="favicon.ico" sizes="any">
<script type="application/ld+json">
{ld_json}
</script>
{FONT_PRELOADS}{INLINE_STYLES}
{style_html}{DESIGN_STYLES}
</head>
<body class="docs-page docs-topic">
<a class="skip-link" href="#main">Skip to content</a>
{site_navigation(guide['slug'])}
<div class="wrap">
<header role="none">
<p class="meta">Live Tennis API &middot; docs &middot; guide</p>
<h1>{E(guide['title'])}</h1>
<p><strong>{E(guide['question'])}</strong> {guide['lede']}</p>
<p class="meta">{guide['meta']}</p>
<nav class="pagenav" aria-label="Related pages">
<a href="./reference.html">Full reference: all endpoints</a>
<a href="./">Interactive reference</a>
<a href="./openapi.yaml">OpenAPI spec</a>
<a href="./changelog.html">Changelog</a>
<a href="{SITE}/pricing">Pricing</a>
<a href="{SITE}/subscribe/free">Free key</a>
</nav>
</header>
<main id="main">
{guide['body'](spec)}</main>
<footer>
<hr>
<nav class="pagenav" aria-label="Other topics">
{siblings}
</nav>
<p class="meta">{guide['footer']}</p>
{CREDIT}
</footer>
</div>
{BEACON}{CLARITY}</body>
</html>
"""
    return pages


def build_robots() -> str:
    return f"""User-agent: *
Allow: /

# Answer engines are explicitly welcome to read and cite this reference.
# The interactive page is client-rendered; reference.html is plain HTML and
# is the one these crawlers can actually read.
User-agent: GPTBot
Allow: /
User-agent: OAI-SearchBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: Claude-SearchBot
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: Google-Extended
Allow: /
User-agent: Claude-User
Allow: /
User-agent: CCBot
Allow: /
# User-fetch and answer agents added 2026-09-14 (SEO/AEO audit WS5).
User-agent: Perplexity-User
Allow: /
User-agent: MistralAI-User
Allow: /
User-agent: DuckAssistBot
Allow: /
User-agent: Applebot
Allow: /
User-agent: Applebot-Extended
Allow: /
User-agent: Amazonbot
Allow: /
User-agent: meta-externalagent
Allow: /
User-agent: Bytespider
Allow: /

Sitemap: {DOCS_URL}/sitemap.xml
"""


def build_sitemap(changelog_date: str = "") -> str:
    # The two hubs first, then one entry per topic page. The topic list is read from TOPICS,
    # not typed here, so a topic cannot exist without being listed (the failure the docs
    # sitemap had for months, at two URLs for a forty-endpoint API).
    pages = [f"{DOCS_URL}/", f"{DOCS_URL}/reference.html"]
    urls = "\n".join(
        f"  <url><loc>{u}</loc><changefreq>weekly</changefreq>"
        f"<priority>{'1.0' if u.endswith('/') else '0.9'}</priority></url>"
        for u in pages
    )
    # A guide carries lastmod because its date is a content fact: the day its claims were last
    # checked against the package, the same date the page shows.
    urls += "\n" + "\n".join(
        f'  <url><loc>{DOCS_URL}/{t["slug"]}.html</loc>'
        + (f'<lastmod>{t["date"]}</lastmod>' if t.get("date") else "")
        + '<changefreq>weekly</changefreq><priority>0.8</priority></url>'
        for t in TOPICS + GUIDES
    )
    if changelog_date:
        # lastmod ONLY here: the newest entry's date is a fact the file itself proves. The two pages
        # above are regenerated on every push, so any date on them would be a deploy time, not a change.
        urls += (f"\n  <url><loc>{DOCS_URL}/changelog.html</loc><lastmod>{changelog_date}</lastmod>"
                 f"<changefreq>weekly</changefreq><priority>0.6</priority></url>")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if generated output is stale")
    args = ap.parse_args()

    spec = load_spec()
    reference = build_html(spec)
    changelog_html, changelog_date = build_changelog(spec, reference)
    topics = build_topic_pages(spec, reference)
    guides = build_guide_pages(spec, reference)
    outputs = {
        DOCS / "reference.html": reference,
        DOCS / "changelog.html": changelog_html,
        **{DOCS / f"{slug}.html": html for slug, html in topics.items()},
        **{DOCS / f"{slug}.html": html for slug, html in guides.items()},
        DOCS / "llms.txt": build_llms_txt(spec),
        DOCS / "robots.txt": build_robots(),
        DOCS / "sitemap.xml": build_sitemap(changelog_date),
        # The same spec as JSON, for the agents and tools that only read JSON (GPT Actions,
        # Postman import, most MCP scaffolds). Both URLs are stable and both are advertised.
        DOCS / "openapi.json": json.dumps(spec, ensure_ascii=False, indent=1) + "\n",
    }

    # Heading levels must not skip. h1 -> h3 is a level a screen reader reports as missing and
    # PageSpeed flags as "Heading elements are not in a sequentially-descending order" — which is
    # how this was found, on pages that had been live for hours: render_operation emits <h3>
    # because on the reference it sits under <h2>Endpoints</h2>, and the topic pages had no <h2>
    # at all. Cheap to assert, invisible otherwise.
    skipped = {}
    for path, content in outputs.items():
        if path.suffix != ".html":
            continue
        levels = [int(m) for m in re.findall(r"<h([1-6])[ >]", content)]
        bad = [(a, b) for a, b in zip(levels, levels[1:]) if b > a + 1]
        if bad:
            skipped[path.name] = bad[:3]
    if skipped:
        raise SystemExit(
            "generated pages skip a heading level: "
            + "; ".join(f"{k} {v}" for k, v in skipped.items())
        )

    # Every page's <title> and meta description must fit the result page: Ahrefs reported the
    # auth page's description at 108 characters and four others past 155, and three titles at
    # 61 or 62. Measured as rendered (entities decoded), on the generated pages and on the
    # hand-written index.html alike.
    out_of_budget = []
    pages_to_check = {p: c for p, c in outputs.items() if p.suffix == ".html"}
    if (DOCS / "index.html").exists():
        pages_to_check[DOCS / "index.html"] = (DOCS / "index.html").read_text(encoding="utf-8")
    for path, content in pages_to_check.items():
        title = html.unescape(re.search(r"<title>(.*?)</title>", content, re.S).group(1).strip())
        meta = re.search(r'<meta name="description" content="([^"]*)"', content)
        desc_len = len(html.unescape(meta.group(1))) if meta else 0
        if len(title) > TITLE_MAX:
            out_of_budget.append(f"{path.name}: title {len(title)} > {TITLE_MAX}")
        if not DESC_MIN <= desc_len <= DESC_MAX:
            out_of_budget.append(f"{path.name}: description {desc_len} not in {DESC_MIN}..{DESC_MAX}")
    if out_of_budget:
        raise SystemExit("pages outside the title/description budget:\n  " + "\n  ".join(out_of_budget))

    # Every JSON-LD block must be JSON an engine can parse, with no HTML entity in it: a script
    # element's text is not decoded, so an entity reaches the parser as literal characters. The
    # players page shipped player&#x27;s in its TechArticle description while its meta tag
    # decoded to player's. The TechArticle description must also be the meta description,
    # decoded, index.html included: two descriptions of one page that disagree are two claims.
    ld_bad = []
    for path, content in pages_to_check.items():
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', content, re.S)
        if not blocks:
            ld_bad.append(f"{path.name}: no JSON-LD block")
            continue
        meta = re.search(r'<meta name="description" content="([^"]*)"', content)
        meta_desc = html.unescape(meta.group(1)) if meta else None
        for block in blocks:
            if re.search(r"&#|&amp;|&quot;", block):
                ld_bad.append(f"{path.name}: HTML entity inside JSON-LD")
            try:
                node = json.loads(block.replace("<\\/", "</"))
            except ValueError as exc:
                ld_bad.append(f"{path.name}: JSON-LD does not parse ({exc})")
                continue
            if node.get("@type") == "TechArticle" and node.get("description") != meta_desc:
                ld_bad.append(f"{path.name}: TechArticle description differs from the meta description")
    if ld_bad:
        raise SystemExit("JSON-LD defects:\n  " + "\n  ".join(ld_bad))

    # Every generated HTML page must carry the beacon. It used to live inside the reference's
    # own template, so the eight topic pages and the changelog were written later and got none
    # of it — nine of eleven docs pages invisible the day the docs stopped being three pages.
    missing_beacon = [
        path.name for path, content in outputs.items()
        if path.suffix == ".html" and "sendBeacon" not in content
    ]
    if missing_beacon:
        raise SystemExit(
            "generated pages with no pageview beacon: " + ", ".join(missing_beacon)
            + "\n  Add {BEACON} before </body> in that template."
        )

    # ...and the on-page behaviour tag, for the same reason: the topic pages were written after
    # the beacon lived in one template and silently got none of it. Both guards or neither.
    missing_clarity = [
        path.name for path, content in outputs.items()
        if path.suffix == ".html" and "clarity.ms" not in content
    ]
    if missing_clarity:
        raise SystemExit(
            "generated pages with no behaviour tag: " + ", ".join(missing_clarity)
            + "\n  Add {CLARITY} before </body> in that template."
        )

    # The README states the spec's size in prose and nothing kept it honest: it read
    # "39 operations (38 paths), 47 schemas" against a spec of 40/39/48 — off by one in three
    # places, on the first file anyone reads about this API. Counted, not trusted.
    readme = ROOT / "README.md"
    if readme.exists():
        want = (
            f"{sum(1 for p in spec['paths'].values() for m in p if m in ('get', 'post', 'put', 'patch', 'delete'))}"
            f" operations ({len(spec['paths'])} paths),"
            f" {len(spec.get('components', {}).get('schemas', {}))} schemas"
        )
        if want not in readme.read_text(encoding="utf-8"):
            raise SystemExit(
                f"README.md does not state the spec's real size.\n  Expected the phrase: {want}"
            )

    # index.html is hand-written (Scalar boots into it), so it is the one page the generator
    # cannot keep in step. Fail loudly rather than let a topic exist with nothing linking to it
    # from the hub: an unlinked page is a page a crawler reaches only through the sitemap.
    index = DOCS / "index.html"
    if index.exists():
        index_html = index.read_text(encoding="utf-8")
        hrefs = set(re.findall(r'href="(?:\./)?([^"#?]+)"', index_html))
        missing = [t["slug"] for t in TOPICS + GUIDES if f'{t["slug"]}.html' not in hrefs]
        if missing:
            raise SystemExit(
                "docs/index.html does not link these topic pages: "
                + ", ".join(missing)
                + "\n  Add them to the static intro AND the noscript fallback (they are kept in sync)."
            )

    if args.check:
        stale = [p.name for p, content in outputs.items()
                 if not p.exists() or p.read_text(encoding="utf-8") != content]
        if stale:
            print(f"STALE (re-run scripts/build_reference.py): {', '.join(stale)}")
            return 1
        print("generated docs are current")
        return 0

    DOCS.mkdir(exist_ok=True)
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)} ({len(content):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
