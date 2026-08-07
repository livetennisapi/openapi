#!/bin/sh
# truthcheck — pins product facts this repo must never contradict.
#
# Forbids copy that was true once and is now wrong (the pre-2026-08-06 quota
# grid, the old docs URL, personal handles) and requires the current anchors
# to be present. CHANGELOG.md is exempt: its dated entries legitimately quote
# the grid as it stood at the time.
set -eu
cd "$(dirname "$0")/.."

files=$(git ls-files | grep -vE '^CHANGELOG\.md$|^scripts/truthcheck\.sh$|\.(png|jpg|jpeg|ico|svg|woff2?)$')

fail=0

forbid() {
    pattern="$1"; why="$2"
    hits=$(printf '%s\n' "$files" | xargs grep -niE "$pattern" 2>/dev/null || true)
    if [ -n "$hits" ]; then
        echo "TRUTHCHECK FAIL — $why:"
        printf '%s\n' "$hits"
        fail=1
    fi
}

# Pre-2026-08-06 day quotas.
forbid '100,?000( *(requests?|reqs?|calls?))? *(per |/) *day|100k *(per |/) *day' \
    'stale PRO day quota (PRO is 10,000/day since 2026-08-06)'
forbid '\bfree\b[^.]*\b1,?000\b[^.]* *(per |/) *day|\bfree\b[^.]*\b1k\b[^.]* *(per |/) *day' \
    'stale FREE day quota (FREE is 100/day since 2026-08-06)'

# Wrong or forbidden references.
forbid 'livetennisapi\.com/docs' 'docs live at docs.livetennisapi.com, not livetennisapi.com/docs'
forbid 'bensynapse' 'personal handle in an org repo'
forbid 'midnight UTC' 'the daily reset is the resets_at instant, never "midnight UTC"'

# This repo states quotas, so the current anchors must be present.
if ! grep -qE '100( *requests?)?/day' openapi.yaml README.md; then
    echo 'TRUTHCHECK FAIL — FREE 100/day not stated anywhere quotas are described'
    fail=1
fi
if ! grep -q 'docs\.livetennisapi\.com' README.md; then
    echo 'TRUTHCHECK FAIL — docs.livetennisapi.com missing from README'
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo 'truthcheck OK'
fi
exit "$fail"
