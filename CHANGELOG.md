# Changelog

All notable changes to the specification are recorded here.

The API surface is versioned as `v1`. Changes within `v1` are **additive only**;
removing a field or changing its type would require `v2`.

## [Unreleased]

### Added
- **History endpoints documented.** `/history/matches/{matchId}` (the full
  point-by-point tape with the per-point model win-probability — BASIC, or
  Historical Data API Starter+), `/history/packages` and
  `/history/packages/{period}` (pre-built monthly bulk downloads, manifest +
  `?format=jsonl|csv` — PRO, Historical Data API Pro+, or a one-off package
  pass), plus the `from`/`to` date-range filter and the 400/403 responses on
  `/history/matches`. New schemas `HistoryTape`, `ModelProfile`,
  `HistoryPackage`. Purely additive.
- **Concrete plan deltas.** `info.description` now states exactly what each
  tier adds over the one below it, with its rate limits (FREE 30/min ·
  1,000/day; BASIC 60/min · 10,000/day; PRO 300/min · 100,000/day; ULTRA
  600/min · 500,000/day), and documents the standalone Historical Data API
  plans (Starter / Pro / Business / one-off passes). `/matches` documents that
  `status=completed` requires BASIC — the gate was always enforced, just not
  written down.
- **WebSocket break-point signals.** The `/ws` subscribe frame now documents an
  optional `signals` array; naming `break_point` opts the connection into two new
  frames — `break_point` (schema `BreakPoint`) the instant a break point arises
  and `break_point_result` (schema `BreakPointResult`) when it resolves. Both are
  ULTRA-only and purely additive: an existing subscriber that sends no `signals`
  sees exactly the frames it saw before. Documented in `info.description`, the
  two new component schemas, and the rendered reference.
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
