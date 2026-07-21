# Changelog

All notable changes to the specification are recorded here.

The API surface is versioned as `v1`. Changes within `v1` are **additive only**;
removing a field or changing its type would require `v2`.

## [Unreleased]

### Added
- **FREE tier.** Self-serve with no card at <https://livetennisapi.com/subscribe/free>
  (30 req/min, 1,000 req/day). Covers live and upcoming matches, scores, players and
  fixtures — the six endpoints now tagged `(FREE)` in their summary. Purely additive:
  no endpoint, field, or type changed, and every paid tier keeps exactly the access it
  had. `/history/matches` remains BASIC; market prices stay PRO; analysis, live model
  fields and the WebSocket feed stay ULTRA.
- `operationId` on all 12 operations, so generated clients get stable method names.
- `info.contact`, `info.license` (MIT) and `info.termsOfService`.
- Redocly lint + a structural contract check in CI.
- Rendered reference published to <https://docs.livetennisapi.com>.

### Changed
- `info.title` is now `Live Tennis API`, matching the product name.
