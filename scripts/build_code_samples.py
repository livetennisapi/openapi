#!/usr/bin/env python3
"""Write the official-client code samples into ``openapi.yaml``.

Every operation in the spec gets an ``x-codeSamples`` list: a curl call, then
one sample for each official client that has a method for it. The interactive
reference shows each sample as a language tab next to the operation.

The samples are generated from ``code-samples/sdk-methods.yaml``, which records
the real method name and call of each client for each operationId. A client
with no method for an operation gets no sample there.

The samples are written straight into ``openapi.yaml``, under the
``operationId`` line of each operation. Only those blocks change. The rest of
the file keeps its comments and layout.

Usage:
    python scripts/build_code_samples.py              # Rewrite the samples in openapi.yaml.
    python scripts/build_code_samples.py --check      # Exit 1 when the map or the samples are out of step.
    python scripts/build_code_samples.py --coverage   # Print which client covers which operation.

``scripts/build_reference.py`` runs the same check. So CI fails when an
operation has no entry in the map, or when the map names an operationId the
spec lacks. It also fails when the samples in the spec are stale.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "openapi.yaml"
METHODS = ROOT / "code-samples" / "sdk-methods.yaml"

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
# The order of the tabs. curl first, then the clients in the order the client
# libraries page lists them.
CLIENT_ORDER = ("python", "js", "go", "php", "dotnet", "dart", "swift", "r")
ENTRY_KEYS = {"call", "print", "returns"}
OPERATION_KEYS = {"result", "params", "body", *CLIENT_ORDER}
KEY_ENV = "LIVETENNISAPI_KEY"

# The block this script owns. It sits right under the operationId line, at the
# same indent, and runs until the next line that is no deeper than that.
OP_INDENT = " " * 6
BLOCK_KEY = "x-codeSamples"
OPERATION_ID_LINE = re.compile(r"^      operationId: (\S+)\s*$")


class MapError(Exception):
    """The method map and the spec disagree, or the map is malformed."""


# --------------------------------------------------------------------- loading


def load_methods(path: Path = METHODS) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MapError(f"{path.name} is not a mapping")
    return data


def spec_operations(spec: dict[str, Any]) -> dict[str, tuple[str, str, dict[str, Any]]]:
    """operationId -> (HTTP method, path, operation object)."""
    ops: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for path, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method in HTTP_METHODS and isinstance(op, dict) and op.get("operationId"):
                ops[op["operationId"]] = (method, path, op)
    return ops


def _parameters(spec: dict[str, Any], path: str, op: dict[str, Any]) -> list[dict[str, Any]]:
    """The operation's parameters with each $ref resolved, path-level ones included."""
    out = []
    for raw in [*spec["paths"][path].get("parameters", []), *op.get("parameters", [])]:
        if "$ref" in raw:
            name = raw["$ref"].rsplit("/", 1)[-1]
            raw = spec["components"]["parameters"][name]
        out.append(raw)
    return out


# ------------------------------------------------------------------ validation


def problems(spec: dict[str, Any], methods: dict[str, Any]) -> list[str]:
    """Every way the map and the spec disagree. An empty list means they agree."""
    found: list[str] = []
    clients = methods.get("clients") or {}
    operations = methods.get("operations") or {}
    ops = spec_operations(spec)

    for key in clients:
        if key not in CLIENT_ORDER:
            found.append(f"clients: unknown client {key!r}")
    for key in CLIENT_ORDER:
        meta = clients.get(key)
        if not isinstance(meta, dict) or not all(meta.get(f) for f in ("label", "lang", "version", "source")):
            found.append(f"clients: {key!r} needs label, lang, version and source")

    for oid in ops:
        if oid not in operations:
            found.append(f"operation {oid!r} is in the spec but has no entry in {METHODS.name}")
    for oid in operations:
        if oid not in ops:
            found.append(f"{METHODS.name} names operation {oid!r}, which the spec does not define")

    for oid, entry in operations.items():
        if oid not in ops:
            continue
        if not isinstance(entry, dict):
            found.append(f"{oid}: the entry is not a mapping")
            continue
        method, path, op = ops[oid]
        for key in entry:
            if key not in OPERATION_KEYS:
                found.append(f"{oid}: unknown key {key!r}")
        result = entry.get("result")
        if not isinstance(result, str) or not re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)*", result):
            found.append(f"{oid}: result must be a snake_case name")

        params = entry.get("params") or {}
        declared = {p["name"]: p for p in _parameters(spec, path, op)}
        for name in params:
            if name not in declared:
                found.append(f"{oid}: params names {name!r}, which the operation does not declare")
        for name, p in declared.items():
            if (p.get("in") == "path" or p.get("required")) and name not in params:
                found.append(f"{oid}: params has no value for the required parameter {name!r}")
        body_required = bool((op.get("requestBody") or {}).get("required"))
        if body_required and not entry.get("body"):
            found.append(f"{oid}: the operation needs a request body and the entry has no body")
        if entry.get("body") and "requestBody" not in op:
            found.append(f"{oid}: the entry has a body and the operation takes none")

        for client in CLIENT_ORDER:
            if client not in entry:
                continue
            value = entry[client]
            if isinstance(value, dict):
                extra = set(value) - ENTRY_KEYS
                if extra:
                    found.append(f"{oid}.{client}: unknown keys {sorted(extra)}")
                call = value.get("call")
                if value.get("returns") not in (None, "error") or (value.get("returns") and client != "go"):
                    found.append(f"{oid}.{client}: returns may only be 'error', and only for go")
            else:
                call = value
            if not isinstance(call, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\(.*\)", call, re.S):
                found.append(f"{oid}.{client}: the call must look like name(arguments)")
    return found


# ------------------------------------------------------------------- rendering


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


def _entry(value: Any) -> tuple[str, str | None, str | None]:
    if isinstance(value, dict):
        return value["call"], value.get("print"), value.get("returns")
    return value, None, None


def _python(call: str, var: str, shown: str | None, _returns: str | None) -> str:
    return (
        "import os\n\n"
        "from livetennisapi import LiveTennisAPI\n\n"
        f'with LiveTennisAPI(api_key=os.environ["{KEY_ENV}"]) as client:\n'
        f"    {var} = client.{call}\n"
        f"    print({shown or var})"
    )


def _js(call: str, var: str, shown: str | None, _returns: str | None) -> str:
    var = _camel(var)
    return (
        "import { LiveTennisAPI } from 'livetennisapi';\n\n"
        f"const client = new LiveTennisAPI({{ apiKey: process.env.{KEY_ENV} }});\n\n"
        f"const {var} = await client.{call};\n"
        f"console.log({shown or var});"
    )


def _go(call: str, var: str, shown: str | None, returns: str | None) -> str:
    var = _camel(var)
    if returns == "error":
        body = (
            f"\tif err := client.{call}; err != nil {{\n"
            "\t\tlog.Fatal(err)\n"
            "\t}\n"
            f'\tfmt.Println("{shown or "done"}")'
        )
    else:
        body = (
            f"\t{var}, err := client.{call}\n"
            "\tif err != nil {\n"
            "\t\tlog.Fatal(err)\n"
            "\t}\n"
            f'\tfmt.Printf("%+v\\n", {shown or var})'
        )
    return (
        "package main\n\n"
        "import (\n"
        '\t"context"\n'
        '\t"fmt"\n'
        '\t"log"\n'
        '\t"os"\n\n'
        '\t"github.com/livetennisapi/livetennisapi-go"\n'
        ")\n\n"
        "func main() {\n"
        f'\tclient := livetennisapi.New(os.Getenv("{KEY_ENV}"))\n'
        "\tctx := context.Background()\n\n"
        f"{body}\n"
        "}"
    )


def _php(call: str, var: str, shown: str | None, _returns: str | None) -> str:
    var = "$" + _camel(var)
    return (
        "use LiveTennisApi\\LiveTennisApi;\n\n"
        f"$client = new LiveTennisApi(getenv('{KEY_ENV}'));\n\n"
        f"{var} = $client->{call};\n"
        f"print_r({shown or var});"
    )


def _dotnet(call: str, var: str, shown: str | None, _returns: str | None) -> str:
    var = _camel(var)
    return (
        "using System.Text.Json;\n"
        "using LiveTennisApi;\n\n"
        f'var apiKey = Environment.GetEnvironmentVariable("{KEY_ENV}")!;\n'
        "using var client = new LiveTennisApiClient(apiKey);\n\n"
        f"var {var} = await client.{call};\n"
        f"Console.WriteLine(JsonSerializer.Serialize({shown or var}));"
    )


def _dart(call: str, var: str, shown: str | None, _returns: str | None) -> str:
    var = _camel(var)
    if shown is None:
        # A list call returns a Page, never null. A single read returns a nullable model.
        # Both keep the decoded JSON in `raw`.
        shown = f"{var}.raw" if re.match(r"(list|search)[A-Z]", call) else f"{var}?.raw"
    return (
        "import 'dart:io';\n\n"
        "import 'package:livetennisapi/livetennisapi.dart';\n\n"
        "Future<void> main() async {\n"
        f"  final apiKey = Platform.environment['{KEY_ENV}']!;\n"
        "  final client = LiveTennisApi(apiKey: apiKey);\n"
        "  try {\n"
        f"    final {var} = await client.{call};\n"
        f"    print({shown});\n"
        "  } finally {\n"
        "    client.close();\n"
        "  }\n"
        "}"
    )


def _swift(call: str, var: str, shown: str | None, _returns: str | None) -> str:
    var = _camel(var)
    return (
        "import Foundation\n"
        "import LiveTennisApi\n\n"
        f'let apiKey = ProcessInfo.processInfo.environment["{KEY_ENV}"] ?? ""\n'
        "let client = LiveTennisApiClient(apiKey: apiKey)\n\n"
        f"let {var} = try await client.{call}\n"
        f"print({shown or var})"
    )


def _r(call: str, var: str, shown: str | None, _returns: str | None) -> str:
    # The R functions take the key as an argument. api_health() needs none.
    key = f'key <- Sys.getenv("{KEY_ENV}")\n' if "key = key" in call else ""
    return (
        "library(livetennisapi)\n\n"
        f"{key}"
        f"{var} <- {call}\n"
        f"print({shown or var})"
    )


RENDER = {"python": _python, "js": _js, "go": _go, "php": _php, "dotnet": _dotnet,
          "dart": _dart, "swift": _swift, "r": _r}


def _curl(spec: dict[str, Any], method: str, path: str, op: dict[str, Any], entry: dict[str, Any]) -> str:
    params = entry.get("params") or {}
    declared = {p["name"]: p for p in _parameters(spec, path, op)}
    url_path = path
    query = []
    for name, value in params.items():
        if declared[name].get("in") == "path":
            url_path = url_path.replace("{" + name + "}", quote(str(value), safe=""))
        else:
            query.append((name, value))
    url = spec["servers"][0]["url"] + url_path
    if query:
        url += "?" + urlencode(query, quote_via=quote)

    first = "curl" if method == "get" else f"curl -X {method.upper()}"
    lines = [f'{first} "{url}"']
    # An operation with `security: []` takes no key.
    if op.get("security", spec.get("security")):
        lines.append(f'-H "Authorization: Bearer ${KEY_ENV}"')
    if entry.get("body"):
        lines.append('-H "Content-Type: application/json"')
        lines.append(f"-d '{json.dumps(entry['body'], separators=(', ', ': '))}'")
    return " \\\n  ".join(lines)


def build_samples(spec: dict[str, Any], methods: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """operationId -> its x-codeSamples list. Call problems() first."""
    clients = methods["clients"]
    out = {}
    for oid, (method, path, op) in spec_operations(spec).items():
        entry = methods["operations"][oid]
        samples = [{"lang": "shell", "label": "curl", "source": _curl(spec, method, path, op, entry)}]
        for client in CLIENT_ORDER:
            if client not in entry:
                continue
            call, shown, returns = _entry(entry[client])
            source = RENDER[client](call, entry["result"], shown, returns)
            samples.append({"lang": clients[client]["lang"], "label": clients[client]["label"],
                            "source": source})
        out[oid] = samples
    return out


# --------------------------------------------------------- writing the spec text


def _block(samples: list[dict[str, str]]) -> list[str]:
    lines = [f"{OP_INDENT}{BLOCK_KEY}:"]
    for sample in samples:
        lines.append(f"{OP_INDENT}  - lang: {sample['lang']}")
        lines.append(f"{OP_INDENT}    label: {json.dumps(sample['label'])}")
        lines.append(f"{OP_INDENT}    source: |-")
        for line in sample["source"].split("\n"):
            lines.append(f"{OP_INDENT}      {line}" if line else "")
    return lines


def strip_blocks(text: str) -> str:
    """The spec text with every block this script wrote removed."""
    out: list[str] = []
    blanks: list[str] = []
    skipping = False
    for line in text.split("\n"):
        if skipping:
            if line == "":
                # A blank line belongs to the block only when the block goes on after it.
                blanks.append(line)
                continue
            if line.startswith(OP_INDENT + " "):
                blanks = []
                continue
            skipping = False
            out.extend(blanks)
            blanks = []
        if line == f"{OP_INDENT}{BLOCK_KEY}:":
            skipping = True
            continue
        out.append(line)
    out.extend(blanks)
    return "\n".join(out)


def render_spec(text: str, samples: dict[str, list[dict[str, str]]]) -> str:
    """Put each operation's samples under its operationId line."""
    out: list[str] = []
    placed = set()
    for line in strip_blocks(text).split("\n"):
        out.append(line)
        match = OPERATION_ID_LINE.match(line)
        if match and match.group(1) in samples:
            oid = match.group(1)
            if oid in placed:
                raise MapError(f"operationId {oid!r} appears twice in {SPEC.name}")
            out.extend(_block(samples[oid]))
            placed.add(oid)
    missing = sorted(set(samples) - placed)
    if missing:
        raise MapError(f"no operationId line at a six-space indent for: {', '.join(missing)}")
    return "\n".join(out)


def generate(text: str, methods: dict[str, Any]) -> str:
    """The spec text with fresh samples, after checking the map against the spec."""
    spec = yaml.safe_load(text)
    found = problems(spec, methods)
    if found:
        raise MapError("\n  ".join(["the method map and the spec disagree:", *found]))
    samples = build_samples(spec, methods)
    new_text = render_spec(text, samples)
    # Read the result back. The samples must parse to exactly what was generated,
    # and nothing else in the spec may change.
    reread = yaml.safe_load(new_text)
    for oid, (_m, _p, op) in spec_operations(reread).items():
        if op.get(BLOCK_KEY) != samples[oid]:
            raise MapError(f"{oid}: the written samples do not read back as generated")
        op.pop(BLOCK_KEY)
    original = yaml.safe_load(strip_blocks(text))
    if reread != original:
        raise MapError("writing the samples changed something else in the spec")
    return new_text


def check(spec_path: Path = SPEC, methods_path: Path = METHODS) -> list[str]:
    """Problems that should fail CI. An empty list means the spec is current."""
    text = spec_path.read_text(encoding="utf-8")
    try:
        new_text = generate(text, load_methods(methods_path))
    except MapError as exc:
        return [str(exc)]
    if new_text != text:
        return [f"the code samples in {spec_path.name} are stale. Run: python scripts/build_code_samples.py"]
    return []


def coverage_table(spec: dict[str, Any], methods: dict[str, Any]) -> str:
    clients = methods["clients"]
    head = "| Operation | " + " | ".join(clients[c]["label"] for c in CLIENT_ORDER) + " |"
    rows = [head, "|---" * (len(CLIENT_ORDER) + 1) + "|"]
    for oid, (method, path, _op) in spec_operations(spec).items():
        entry = methods["operations"].get(oid, {})
        cells = []
        for client in CLIENT_ORDER:
            if client in entry:
                name = _entry(entry[client])[0].split("(", 1)[0]
                cells.append(f"`{name}`")
            else:
                cells.append("no")
        rows.append(f"| `{oid}` {method.upper()} `{path}` | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if the map or the samples are out of step")
    mode.add_argument("--coverage", action="store_true", help="print the coverage table as Markdown")
    args = ap.parse_args()

    if args.coverage:
        print(coverage_table(yaml.safe_load(SPEC.read_text(encoding="utf-8")), load_methods()))
        return 0
    if args.check:
        found = check()
        for problem in found:
            print(problem)
        if found:
            return 1
        print("code samples are current")
        return 0

    text = SPEC.read_text(encoding="utf-8")
    try:
        new_text = generate(text, load_methods())
    except MapError as exc:
        print(exc)
        return 1
    if new_text != text:
        SPEC.write_text(new_text, encoding="utf-8")
        print(f"wrote the code samples into {SPEC.name}")
    else:
        print("code samples already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
