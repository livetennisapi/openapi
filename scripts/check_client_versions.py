#!/usr/bin/env python3
"""Check the client libraries page against the registries.

``docs/client-libraries.html`` is built from the CLIENTS table in ``build_reference.py``. This
script reads each package's registry again and compares three things with that table: the newest
published version, the minimum runtime the registry states, and the licence. It needs the network,
so it is not part of ``build_reference.py --check``. Run it by hand after a client release and
before a change to the page.

Usage:
    python scripts/check_client_versions.py          # exit 1 when a row is behind
    python scripts/check_client_versions.py --json   # the same findings as JSON

Exit status: 0 when every row matches, 1 when a row is behind its registry, 2 when a registry
could not be read and no row is known to be behind.

Sources, one per registry kind:
    pypi        https://pypi.org/pypi/NAME/json
    npm         https://registry.npmjs.org/NAME/latest
    go          https://proxy.golang.org/MODULE/@latest and /@v/VERSION.mod
    packagist   https://repo.packagist.org/p2/VENDOR/NAME.json
    nuget       https://api.nuget.org/v3-flatcontainer/ID/index.json and the .nuspec
    pub         https://pub.dev/api/packages/NAME
    r-universe  https://UNIVERSE.r-universe.dev/api/packages/NAME
    github-tag  https://api.github.com/repos/OWNER/REPO/tags and the tagged Package.swift
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_reference  # noqa: E402

USER_AGENT = "livetennisapi-docs-client-check/1.0 (+https://docs.livetennisapi.com)"
TIMEOUT = 30


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def fetch_json(url: str) -> Any:
    return json.loads(fetch(url))


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version.split("+")[0]))


def is_stable(version: str) -> bool:
    # Build metadata after "+" does not make a release a pre-release. A "-" suffix does.
    return re.fullmatch(r"v?\d+(\.\d+)*(\+[0-9A-Za-z.-]+)?", version) is not None


def newest(versions: list[str]) -> str:
    stable = [v for v in versions if is_stable(v)]
    if not stable:
        raise ValueError("the registry lists no stable version")
    return max(stable, key=version_key).lstrip("v").split("+")[0]


def read_pypi(name: str) -> dict[str, str | None]:
    info = fetch_json(f"https://pypi.org/pypi/{name}/json")["info"]
    # `license_expression` is an SPDX expression and is always compared. The older free-text
    # `license` field can hold a whole licence text, which is not a name to compare.
    licence = info.get("license_expression")
    if not licence:
        legacy = (info.get("license") or "").strip()
        licence = legacy if legacy and len(legacy) <= 40 and "\n" not in legacy else None
    return {"version": info["version"], "runtime": info.get("requires_python"), "licence": licence}


def read_npm(name: str) -> dict[str, str | None]:
    latest = fetch_json(f"https://registry.npmjs.org/{name}/latest")
    return {"version": latest["version"], "runtime": (latest.get("engines") or {}).get("node"),
            "licence": latest.get("license")}


def read_go(module: str) -> dict[str, str | None]:
    version = fetch_json(f"https://proxy.golang.org/{module}/@latest")["Version"]
    mod = fetch(f"https://proxy.golang.org/{module}/@v/{version}.mod").decode()
    go_line = re.search(r"^go (\S+)$", mod, re.M)
    # The module proxy carries no licence field. The row's licence is the repository's LICENSE.
    return {"version": version.lstrip("v"), "runtime": go_line.group(1) if go_line else None, "licence": None}


def read_packagist(name: str) -> dict[str, str | None]:
    answer = fetch_json(f"https://repo.packagist.org/p2/{name}.json")
    releases = answer["packages"][name]
    if answer.get("minified") == "composer/2.0":
        # A minified p2 file gives each release only the keys that differ from the release before
        # it, and "__unset" for a key that is gone. Rebuild every release in full.
        full: list[dict[str, Any]] = []
        current: dict[str, Any] = {}
        for delta in releases:
            current = {**current, **delta}
            current = {key: value for key, value in current.items() if value != "__unset"}
            full.append(current)
        releases = full
    version = newest([r["version"] for r in releases])
    release = next(r for r in releases if is_stable(r["version"]) and r["version"].lstrip("v").split("+")[0] == version)
    licence = release.get("license") or []
    return {"version": version, "runtime": (release.get("require") or {}).get("php"),
            "licence": licence[0] if licence else None}


def read_nuget(package_id: str) -> dict[str, str | None]:
    base = f"https://api.nuget.org/v3-flatcontainer/{package_id}"
    version = newest(fetch_json(f"{base}/index.json")["versions"])
    nuspec = fetch(f"{base}/{version}/{package_id}.nuspec").decode()
    frameworks = sorted(set(re.findall(r'<group targetFramework="([^"]+)"', nuspec)))
    licence = re.search(r'<license type="expression">([^<]+)</license>', nuspec)
    return {"version": version, "runtime": ", ".join(frameworks) or None,
            "licence": licence.group(1) if licence else None}


def read_pub(name: str) -> dict[str, str | None]:
    latest = fetch_json(f"https://pub.dev/api/packages/{name}")["latest"]
    # pub.dev has no licence field in this API. The row's licence is the package's LICENSE file.
    return {"version": latest["version"],
            "runtime": (latest["pubspec"].get("environment") or {}).get("sdk"), "licence": None}


def read_r_universe(identifier: str) -> dict[str, str | None]:
    universe, name = identifier.split("/")
    package = fetch_json(f"https://{universe}.r-universe.dev/api/packages/{name}")
    r_dep = next((d for d in package.get("_dependencies", []) if d.get("package") == "R"), {})
    licence = (package.get("License") or "").split(" ")[0] or None
    return {"version": package["Version"], "runtime": r_dep.get("version"), "licence": licence}


def read_github_tag(repo: str) -> dict[str, str | None]:
    tags = [t["name"] for t in fetch_json(f"https://api.github.com/repos/{repo}/tags?per_page=100")]
    version = newest(tags)
    tag = next(t for t in tags if is_stable(t) and t.lstrip("v").split("+")[0] == version)
    manifest = fetch(f"https://raw.githubusercontent.com/{repo}/{tag}/Package.swift").decode()
    tools = re.search(r"swift-tools-version:\s*(\S+)", manifest)
    return {"version": version, "runtime": tools.group(1) if tools else None, "licence": None}


def same_licence(stated: str, expected: str) -> bool:
    """MIT, "MIT License" and "MIT licence" are one licence. "MIT-0" and "MIT OR Apache-2.0" are not."""
    words = stated.strip().split()
    return bool(words) and words[0] == expected and all(w.lower() in ("license", "licence") for w in words[1:])


READERS = {"pypi": read_pypi, "npm": read_npm, "go": read_go, "packagist": read_packagist,
           "nuget": read_nuget, "pub": read_pub, "r-universe": read_r_universe,
           "github-tag": read_github_tag}


def check(client: dict[str, Any]) -> dict[str, Any]:
    kind, identifier = client["source"]
    result: dict[str, Any] = {"key": client["key"], "package": client["package"], "registry": kind,
                              "page_version": client["version"], "problems": [], "unreadable": None}
    try:
        found = READERS[kind](identifier)
    except (OSError, http.client.HTTPException, ValueError, LookupError, TypeError, AttributeError,
            StopIteration) as exc:
        # The network failed or the registry answered in a shape this script does not know.
        # Neither says the row is behind, so it is reported apart from a real difference.
        result["unreadable"] = f"{type(exc).__name__}: {exc}"
        return result
    result["registry_version"] = found["version"]
    if found["version"] != client["version"]:
        result["problems"].append(f"the page says {client['version']}, the registry has {found['version']}")
    if found["runtime"] != client["runtime_spec"]:
        result["problems"].append(
            f"the page records the runtime as {client['runtime_spec']!r}, the registry states {found['runtime']!r}")
    if found["licence"] is not None and not same_licence(found["licence"], build_reference.CLIENTS_LICENCE):
        result["problems"].append(
            f"the page says {build_reference.CLIENTS_LICENCE}, the registry states {found['licence']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="print the findings as JSON")
    args = parser.parse_args()

    results = [check(client) for client in build_reference.CLIENTS]
    behind = [r for r in results if r["problems"]]
    unreadable = [r for r in results if r["unreadable"]]
    if args.json:
        print(json.dumps(results, indent=1))
    else:
        for r in results:
            state = "BEHIND" if r["problems"] else "UNREAD" if r["unreadable"] else "ok"
            print(f"{state:6} {r['key']:10} {r['package']} {r['page_version']} ({r['registry']})")
            for problem in r["problems"]:
                print(f"         {problem}")
            if r["unreadable"]:
                print(f"         could not read the registry: {r['unreadable']}")
        matched = len(results) - len(behind) - len(unreadable)
        print(f"{matched} of {len(results)} rows match their registry"
              f" (page checked {build_reference.CLIENTS_CHECKED})")
    if behind:
        return 1
    return 2 if unreadable else 0


if __name__ == "__main__":
    sys.exit(main())
