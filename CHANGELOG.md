# Changelog

All notable changes to the specification are recorded here.

The API surface is versioned as `v1`. Changes within `v1` are **additive only**;
removing a field or changing its type would require `v2`.

## [1.1.0] — 2026-08-02

### Added
- **Usage endpoint.** `GET /usage` (FREE — any tier): your own durable daily
  usage vs quota — tier, limits, today's calls and a 30-day history. Calls to
  it are quota-exempt. New schema `Usage`.
- **As-of rankings.** `GET /rankings` (ULTRA): ranking records as they stood on
  a date — `player` (required, repeatable, max 50), `as_of`, and `system`
  (`atp`, `wta`, `itf_jt`, `itf_mt`, `itf_wt`, `utr`). Systems are never
  collapsed into a single "rank"; UTR carries a rating with null rank/points.
  `meta.coverage.oldest_available` gives the earliest date each system can
  answer for. New schemas `RankingRecord`, `RankingListMeta`.
- **In-play match statistics.** `GET /matches/{matchId}/statistics` (ULTRA):
  two families, deliberately never merged — DERIVED (rebuilt from the
  point-by-point record: hold/break %, break points, service & return points)
  and MEASURED (counted upstream: aces, double faults, the serve split,
  winners/unforced errors). Each family carries its own `coverage`, `as_of`
  and `age_seconds`; absent measured fields are omitted, never zero-filled;
  `coverage: none` on both families is a 200 with null `players`, not a 404;
  a divergence guard withholds measured values when the families disagree.
  New schemas `MatchStatistics`, `MatchStatisticsSide`,
  `MatchStatisticsMeasured`, `MatchStatisticsFreshness`,
  `MatchStatisticsFamily`.
- **Webhooks.** `POST /webhooks`, `GET /webhooks`,
  `DELETE /webhooks/{webhookId}` (ULTRA, direct keys only): we POST the same
  frames the WebSocket sends to your HTTPS endpoint. Deliveries carry
  `X-LTAPI-Signature` (`sha256=<hex>` HMAC-SHA256 over the raw body),
  `X-LTAPI-Timestamp` and `X-LTAPI-Event`; up to 3 webhooks per key
  (`409 webhook_limit`); auto-disable after 25 consecutive failures. The
  signing secret is returned exactly once, on the 201. New schema `Webhook`.
- **Bare price ticks.** `GET /matches/{matchId}/prices` (PRO): recent ticks of
  the mapped match-winner market without the market wrapper — `limit` caps at
  500, `minutes` bounds the lookback, 404 when the match has no mapped market.
- **Tape coverage and sequence.** `/history/matches` gains `?coverage=` (items
  are now `HistoryMatch` — `Match` plus a `tape` coverage object);
  `/history/matches/{matchId}` gains `?sequence=raw|clean`, documents that it
  works on a LIVE match, and its `meta` now carries `coverage`,
  `point_source`, `raw_rows`, `unique_states` and `sequence`. Tape rows are
  now the explicit `HistoryTapeRow` (null `timestamp` marks a reconstructed
  row). New schemas `Coverage`, `HistoryMatch`, `HistoryTapeRow`.
- **Rankings packages.** `/history/packages` and `/history/packages/{period}`
  gain `?kind=tape|rankings` (default `tape`) and the listing gains
  `?year=YYYY` for the year-archive view; `HistoryPackage` documents the
  `kind` field and that JSONL is one line per match while CSV is one row per
  point.
- **List meta.** `ListMeta` now declares `total` (nullable — null when the set
  cannot be counted cheaply) and `has_more` (page on this, not on `count`).
- **Error hints.** `Error` now declares `detail` (human-readable explanation)
  and `allowed` (accepted values on a rejected enumerated parameter).
- **Price provenance.** `Price` gains `price_source` and `synthetic`, so a
  quote synthesised from mid is never mistaken for a live order book.
- **Profile provenance.** The `Analysis` profile (and `ModelProfile`) gains
  `stage` (`pregame` | `live` | null = unknown), `model_version`, and — on
  `Analysis` — `input_state`, the score an in-play forecast actually saw.
- **CORS documented.** `info.description` now states that the REST surface
  sends `Access-Control-Allow-Origin: *` (GET/OPTIONS, no credentials mode)
  and that a FREE key in browser code is acceptable while a paid key belongs
  server-side.
- **WebSocket subscribe frame.** `info.description` now shows the full
  subscribe frame keys — `action`, `topics` and the optional `signals` list.

### Changed
- `info.version` is now `1.1.0`.
- `GET /matches/{matchId}/score` documents that it is a point-in-time
  snapshot, pointing at `/history/matches/{matchId}?sequence=clean` for the
  sequence of states and `/matches/{matchId}/statistics` for in-play
  statistics.

The entries below were previously listed as Unreleased and ship in this
release.

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
- **Rendered reference: correct plan labels + plans/FAQ pages.** The tier
  parser labelled `GET /matches/{matchId}` as ULTRA (highest-tier-wins scan
  over "(FREE; +market PRO, +analysis ULTRA)") and did not recognise FREE at
  all, so every FREE endpoint showed "Plan required: —". It now takes the
  first tier named. The Plans section gained the FREE row, per-tier daily
  caps, the standalone Historical Data API plans (Starter / Pro / Business /
  one-off passes), the Break-point Alerts plans (Free vs Pro), and a FAQ
  ("How much data can I access on each plan?", "How far back does history
  go?", "What's in the point-by-point tape?"). Operation descriptions are now
  rendered, and `llms.txt` mirrors all of it.
- `info.title` is now `Live Tennis API`, matching the product name.
