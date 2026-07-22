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
                return {**merged, **rest}
            return merged
        return {k: resolve(v, spec, _seen) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve(v, spec, _seen) for v in node]
    return node


def tier_of(summary: str) -> str:
    """Read the plan out of the operation summary, e.g. '… (PRO)' -> 'PRO'."""
    for tier in ("ULTRA", "PRO", "BASIC"):
        if tier in (summary or ""):
            return tier
    return "—"


def type_of(schema: dict[str, Any]) -> str:
    """Render a JSON Schema type as compact human text."""
    if not isinstance(schema, dict):
        return "—"
    if "_cycle" in schema:
        return schema["_cycle"]
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
    return str(t or "object")


def fields_of(schema: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Flatten a schema's properties into (name, type, description) rows.

    Merges ``allOf`` branches, so a composed schema like ``MatchDetail``
    (``Match`` + extra embeds) renders its full field set rather than nothing.
    """
    if not isinstance(schema, dict):
        return []

    props: dict[str, Any] = {}
    for branch in schema.get("allOf", []):
        if isinstance(branch, dict) and isinstance(branch.get("properties"), dict):
            props.update(branch["properties"])
    if isinstance(schema.get("properties"), dict):
        props.update(schema["properties"])

    rows = []
    for name, sub in props.items():
        if not isinstance(sub, dict):
            continue
        rows.append((name, type_of(sub), sub.get("description", "")))
    return rows


# ------------------------------------------------------------------ rendering

E = html.escape


def md_inline(text: str) -> str:
    """Minimal markdown: backtick code and bare URLs, escaped first.

    The bare-URL half of that promise was never implemented, which is why the
    spec's own FREE-signup URL rendered as dead plain text — the one link in the
    description a reader most wants to click. Autolinking happens after escaping
    and skips anything already inside a tag, so it cannot produce nested markup.
    """
    out = E(text or "")
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    # Trailing punctuation is sentence punctuation, not part of the URL.
    out = re.sub(
        r"(?<![\"'=>])(https?://[^\s<>()\"']+[^\s<>()\"'.,;:])",
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
        f"<tr><td><code>{E(n)}</code></td><td>{E(t)}</td><td>{md_inline(d)}</td></tr>"
        for n, t, d in rows
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


def render_operation(path: str, method: str, op: dict[str, Any], spec: dict[str, Any]) -> str:
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

    params = [resolve(p, spec) for p in op.get("parameters", [])]
    if params:
        rows = []
        for p in params:
            if not isinstance(p, dict):
                continue
            sch = p.get("schema", {}) or {}
            default = sch.get("default")
            extra = f" Default <code>{E(str(default))}</code>." if default is not None else ""
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
                f"<tr><td><code>{E(n)}</code></td><td>{E(t)}</td><td>{md_inline(d)}</td></tr>"
                for n, t, d in rows
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

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(info['title'])} — Full API Reference (text)</title>
<meta name="description" content="Complete text reference for the Live Tennis API: every endpoint, parameter, response field and plan tier. Real-time tennis scores, players, rankings, match-winner odds and model win-probability for ATP, WTA, Challenger and ITF.">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{DOCS_URL}/reference.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{E(info['title'])} — Full API Reference">
<meta property="og:url" content="{DOCS_URL}/reference.html">
<meta property="og:image" content="{DOCS_URL}/banner.jpg">
<link rel="icon" href="favicon.ico" sizes="any">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"TechArticle",
"headline":"{E(info['title'])} — Full API Reference",
"description":"Complete text reference for every Live Tennis API endpoint, parameter, response field and plan tier.",
"url":"{DOCS_URL}/reference.html",
"inLanguage":"en",
"isPartOf":{{"@type":"WebSite","name":"Live Tennis API","url":"{SITE}"}},
"publisher":{{"@type":"Organization","name":"Live Tennis API","url":"{SITE}","logo":"{DOCS_URL}/icon-256.png"}}}}
</script>
<link rel="preload" href="fonts/inter-latin-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="fonts.css">
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
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<div class="wrap">

<header>
<h1>{E(info['title'])} — Full Reference</h1>
<p class="meta">Version {E(str(info.get('version','')))} &middot; OpenAPI {E(str(spec.get('openapi','')))}</p>
<nav class="pagenav" aria-label="Related pages">
<a href="./">Interactive reference</a>
<a href="./openapi.yaml">OpenAPI spec</a>
<a href="{SITE}">livetennisapi.com</a>
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
<li><a href="#conventions">Conventions</a></li>
<li><a href="#endpoints">Endpoints</a> — all {len(toc)}, with parameters and responses</li>
<li><a href="#websocket">WebSocket feed (ULTRA)</a></li>
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
<div class="scrollx" tabindex="0" role="region" aria-label="Plans and pricing">
<table><caption class="vh">Plans — what each tier unlocks, its rate limit and price</caption>
<thead><tr><th scope="col">Plan</th><th scope="col">Unlocks</th><th scope="col">Rate limit</th><th scope="col">Price</th></tr></thead><tbody>
<tr><th scope="row">BASIC</th><td>Matches, scores, players, fixtures, history</td><td>60/min &middot; 10,000/day</td><td>$9.99/mo</td></tr>
<tr><th scope="row">PRO</th><td>Adds match events and market prices</td><td>300/min &middot; 100,000/day</td><td>$29.99/mo</td></tr>
<tr><th scope="row">ULTRA</th><td>Adds model analysis, <code>win_probability_p1</code>, <code>danger</code>, and the WebSocket feed</td><td>600/min &middot; 500,000/day</td><td>$99.99/mo</td></tr>
</tbody></table></div>
<p class="scrollnote">The table above scrolls sideways.</p>
<p>Calling an endpoint above your plan returns <code>403 {{"error":"upgrade_required"}}</code> —
never a silent empty result. <a href="{SITE}/#pricing">See pricing</a>.</p>

<h2 id="clients">Official client libraries</h2>
<div class="scrollx" tabindex="0" role="region" aria-label="Official client libraries">
<table class="linkrow"><caption class="vh">Official client libraries — install command and source repository</caption>
<thead><tr><th scope="col">Language</th><th scope="col">Install</th><th scope="col">Source</th></tr></thead><tbody>
<tr><th scope="row">Python</th><td><code>pip install livetennisapi</code></td><td><a href="https://github.com/livetennisapi/livetennisapi-python">livetennisapi-python</a></td></tr>
<tr><th scope="row">JavaScript / TypeScript</th><td><code>npm install livetennisapi</code></td><td><a href="https://github.com/livetennisapi/livetennisapi-js">livetennisapi-js</a></td></tr>
<tr><th scope="row">MCP server (LLM agents)</th><td><code>npx livetennisapi-mcp</code></td><td><a href="https://github.com/livetennisapi/livetennisapi-mcp">livetennisapi-mcp</a></td></tr>
</tbody></table></div>

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
<code>{{"action":"subscribe","topics":["live-scores"]}}</code> or
<code>{{"action":"subscribe","topics":["match:&lt;id&gt;"]}}</code>. The server acknowledges with a
<code>subscribed</code> frame, then pushes <code>score</code> frames on every change plus a
<code>ping</code> heartbeat roughly every 15 seconds.</p>

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
</footer>

</div>
</body>
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
        "> WTA, Challenger and ITF, over REST and WebSocket.",
        "",
        f"Base URL: {base}",
        f"Full text reference: {DOCS_URL}/reference.html",
        f"OpenAPI spec: {DOCS_URL}/openapi.yaml",
        f"Website: {SITE}",
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
        "## Plans",
        "- BASIC ($9.99/mo) — matches, scores, players, fixtures, history. 60 req/min.",
        "- PRO ($29.99/mo) — adds match events and market prices. 300 req/min.",
        "- ULTRA ($99.99/mo) — adds model analysis, win probability and WebSocket. 600 req/min.",
        "",
        "Calling above your plan returns 403 {\"error\":\"upgrade_required\"}.",
        "",
        "## Endpoints",
    ]
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            lines.append(f"- {method.upper()} {path} — {op.get('summary','')}")
    lines += [
        "",
        "## Official client libraries",
        "- Python: `pip install livetennisapi` — https://github.com/livetennisapi/livetennisapi-python",
        "- JavaScript/TypeScript: `npm install livetennisapi` — https://github.com/livetennisapi/livetennisapi-js",
        "- MCP server for LLM agents: `npx livetennisapi-mcp` — https://github.com/livetennisapi/livetennisapi-mcp",
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

Sitemap: {DOCS_URL}/sitemap.xml
"""


def build_sitemap() -> str:
    pages = [f"{DOCS_URL}/", f"{DOCS_URL}/reference.html"]
    urls = "\n".join(
        f"  <url><loc>{u}</loc><changefreq>weekly</changefreq>"
        f"<priority>{'1.0' if u.endswith('/') else '0.9'}</priority></url>"
        for u in pages
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail if generated output is stale")
    args = ap.parse_args()

    spec = load_spec()
    outputs = {
        DOCS / "reference.html": build_html(spec),
        DOCS / "llms.txt": build_llms_txt(spec),
        DOCS / "robots.txt": build_robots(),
        DOCS / "sitemap.xml": build_sitemap(),
    }

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
