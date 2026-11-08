"""Derive the spec copy oapi-codegen can read. Nothing here changes the API.

oapi-codegen builds on kin-openapi and reads OpenAPI 3.0. Two things in
our 3.1 document stop it:

1. `components.parameters.player` and `components.schemas.Player` both
   become the Go type `Player`. The parameter gets `x-go-name: PlayerIDs`.
2. A nullable enum lists `null` among its values (`enum: [1, 2, null]`).
   oapi-codegen tries to write `null` as a Go constant. The `null` is
   dropped from the list. The `type: [..., "null"]` beside it still says
   the field can be null.

    python3 oapi_codegen_prep.py [--rename-only] IN.json OUT.json

`--rename-only` applies the first change alone, to show the second one is
needed too.
"""
from __future__ import annotations

import json
import sys


def drop_null_enums(node: object) -> int:
    count = 0
    if isinstance(node, dict):
        enum = node.get("enum")
        if isinstance(enum, list) and None in enum:
            node["enum"] = [v for v in enum if v is not None]
            count += 1
        for value in node.values():
            count += drop_null_enums(value)
    elif isinstance(node, list):
        for value in node:
            count += drop_null_enums(value)
    return count


def main(src: str, dst: str, rename_only: bool = False) -> None:
    with open(src, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec["components"]["parameters"]["player"]["x-go-name"] = "PlayerIDs"
    dropped = 0 if rename_only else drop_null_enums(spec)
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(spec, fh)
    print(f"oapi-codegen prep: renamed 1 parameter type, dropped null from {dropped} enums")


if __name__ == "__main__":
    args = sys.argv[1:]
    only = "--rename-only" in args
    paths = [a for a in args if a != "--rename-only"]
    main(paths[0], paths[1], rename_only=only)
