# Changelog

All notable changes to the specification are recorded here.

The API surface is versioned as `v1`. Changes within `v1` are **additive only**;
removing a field or changing its type would require `v2`.

## [1.4.0] — 2026-08-16

### Added
- **Live per-point events.** `GET /matches/{matchId}/points` (ULTRA) — the
  live per-point event stream of one match in `seq` order, paged with
  `?after_seq=` (the resume cursor; up to 500 rows per page, continue on
  `last_seq` while `has_more`). It is the REST catch-up for the WebSocket
  `point` frames, which are best-effort with no replay. Per-match
  `pbp_coverage` states honestly whether the match has a true per-point
  stream (`point`) or only the snapshot score path (`game` — `points` empty,
  an answer rather than an error); per-point coverage is never promised
  slate-wide. New schemas `MatchPoints`, `LivePoint` and `PointFrame`; new
  error codes `bad_after_seq` and `points_disabled` (the surface switched
  off server-side).
- **WebSocket `points` signal.** The native `/ws` feed's `signals` array may
  now name `points` to opt into one `point` frame (schema `PointFrame`) per
  persisted point of the subscribed matches. Config-gated, off by default —
  the `subscribed` ack echoes the signals actually active. The push feed
  carries the same frames on their own channel family
  (`point:match:{match_id}`, `point:slate`), deliberately separate from the
  score channels; webhooks gain the matching `point` event (one POST per
  live point, `X-LTAPI-Event: point`). Point frames are events, not states —
  a missed one does not self-correct; recovery is the REST catch-up read.
- **Point-complete tape reads.** `?points=default|complete` on
  `GET /history/matches/{matchId}`: `complete` opts out of
  observed-rows-first precedence and serves a whole-match reconstruction
  WHOLE, in point order, where one exists (`point_winner` on every row, null
  timestamps/model fields per the reconstruction contract); where none
  exists the response is the default read plus `meta.points` — no error.
  Cannot combine with `sequence=clean` (400 `bad_combination`); an unknown
  value is a 400 `bad_points`; where not yet enabled, `complete` answers
  400 `points_read_disabled` rather than silently serving the default. The
  tape's `meta.points` block (schema `PointsMeta`) reports the measured
  point-completeness of exactly the sequence returned — computed at read
  time, per match, never a stored blanket claim.
- **Point-completeness on the listing.** `HistoryMatch.tape` gains
  `points_complete` (bool|null — the nightly ledger's best-basis verdict;
  null means not yet measured, never a guess) and `completeness`
  (0..1|null), and `GET /history/matches` gains the
  `?points_complete=true|false` filter (applied after the page is cut,
  exactly like `?coverage=`; anything but true/false is a 400
  `bad_points_complete`).

### Changed
- **Model win-probability copy tells the truth about density.** The plan and
  FAQ copy no longer claims the tape carries the model win-probability "at
  every point" / "per point": the model stamp is best-effort and rides the
  rows where the model ran — `meta.model_rows` is the count, and null is the
  honest value elsewhere. The current-score snapshot is described as
  overwritten on every score commit, not "on every point".
- `HistoryTapeRow.point_winner` is documented on `?points=complete` rows as
  well as `?sequence=clean` (there the served order IS point order).
- `info.version` is now `1.4.0`.

## [1.3.1] — 2026-08-07

### Added
- **`kind=rally` bulk packages documented.** The `/history/packages` `kind`
  enum gains `rally` — the charted rally corpus (shot-by-shot) as YEARLY
  exports, ULTRA, `period` = `YYYY` like `archive`. The kind has been live
  in the API (it shipped alongside the per-match rally endpoints); the spec
  simply did not list it. Additive only: the enum, the `HistoryPackage.kind`
  field, and the package-shape prose now match the served surface —
  `kind` accepts `tape` (default), `rankings` (ULTRA), `rally` (ULTRA)
  and `archive`.

## [1.3.0] — 2026-08-07

### Added
- **Shot-level charting.** `GET /charting/players` (ULTRA) — career
  serve/return profile from the Match Charting Project: serve placement
  (deuce/ad × wide/body/T), return depth and outcomes, net and
  serve-and-volley conversion, clutch break/game/set-point serving and
  returning, winners and unforced errors by wing, rally-length and
  shot-direction tendencies, summed over the player's charted matches
  (`name` keyed, `gender=men|women` disambiguates, ambiguous fragments
  refused with candidates). `GET /charting/matches/{chartingMatchId}`
  (ULTRA) — every stat family for one charted match, both players, per-set
  split. Coverage is curated: 11,646 charted matches back to the 1960s,
  concentrated on the majors, not full-slate.
- **Push-feed token.** `GET /ws-token` (ULTRA): mints a short-lived signed
  token plus the push WebSocket URL and channel vocabulary —
  `match:{match_id}` per-match streams and `slate:all` for every live score
  frame. A separate high-fan-out surface from the native `/ws` feed.
- **H2H stat splits.** On ULTRA, `GET /h2h` adds a per-player `stats` block:
  serve/return/break-point aggregates over the pairing — `archive_serve`
  (serve-side, from 1991) and `current` (2023+, adding return and
  break-point conversion, aces and winners), each with
  `meetings_with_stats`.
- **Abuse throttle documented.** The 429 family now documents all three body
  shapes: the per-minute limit (`rate_limited` with `upgrade_url`/`tier`/
  `price`), the per-day quota (`rate_limited` with `scope: "day"`,
  `limit_per_day` and `resets_at` — an absolute ISO instant), and
  `abuse_throttled` with `retry_at_epoch` — a 24-hour block for clients
  hammering far past their cap, which a well-behaved retry loop never sees.

### Changed
- **2026-08-06 quota grid re-set (recorded here retroactively).** On
  2026-08-06 the daily quotas were cut, with no grandfathering: FREE
  100/day (was 1,000), BASIC 1,000/day (was 10,000), PRO 10,000/day (was
  100,000); ULTRA unchanged at 500,000/day; per-minute limits unchanged
  (30/60/300/600). The shipped 1.2.0 spec text was edited in place on that
  date without a version bump — this entry is the changelog record of that
  change. Older entries below quote the pre-cut grid as it stood then.
- **Tours.** Coverage phrasing is now the five tours everywhere — ATP, WTA,
  Challenger, ITF and juniors — matching the `tour` filter enum
  (`atp, wta, challenger, itf, juniors`).
- **WebSocket copy.** The subscribe frame is documented as
  `{"topics":["live-scores"]}` (+ optional `signals`) — the previously shown
  `action` key is not read by the server. Score frames are documented as
  carrying the ULTRA model fields (`win_probability_p1`, `danger`) live — a
  null means the model had no output for that point. The 2-connections-per-
  key limit is stated.
- `info.version` is now `1.3.0`.

## [1.2.0] — 2026-08-03

### Added
- **Results archive (1968–2022).** The history product now runs in two
  continuous, non-overlapping halves: the point-by-point tape (2023→now) and
  the results archive (1968–2022). Four new endpoints, all BASIC (or any
  Historical Data API plan): `GET /history/archive/matches` (winner/loser-
  shaped results — ATP and WTA, main draws, qualifying and the ITF/futures
  tiers, 1968 through 2022, with final score, seeds, ranks at the time;
  filters `tour`, `name`, `from`/`to`, `round`, `level`; its own id space;
  `event_date` is the TOURNAMENT START date; ends 2022-12-31, exactly where
  the tape begins), `GET /history/archive/matches/{archiveId}` (one result,
  with per-match serve statistics where the era recorded them — null before
  1991 mostly, never synthesised), `GET /history/archive/players` (bios +
  career-high rank and the week it was first reached), and
  `GET /history/archive/career` (career aggregates — sums and ratios of sums
  only; `serve.matches_with_stats` states the serve-stat coverage). New
  schemas `ArchiveMatch`, `ArchivePlayer`, `ArchivePlayerBio`,
  `ArchiveCareer`.
- **Head-to-head.** `GET /h2h?p1=&p2=` (BASIC, or any History plan): the
  record between two players across both halves of the product. Name-keyed;
  an ambiguous fragment is refused with the candidate list
  (`400 ambiguous_name`); totals count meetings with a known winner and
  `undecided` counts the rest; every meeting carries `outcome` so walkovers
  and retirements can be excluded. New schema `HeadToHead`.
- **Rally construction.** `GET /rally/matches`,
  `GET /rally/matches/{rallyMatchId}` and
  `GET /history/matches/{matchId}/rally` (all ULTRA): shot-by-shot charted
  data — serve direction, every stroke with wing/direction/depth, rally
  length, how the point ended. Its own id space (`rally_match_id`);
  `404 not_charted` distinguishes "we hold the match but nobody charted it"
  from "no such match". New schemas `RallyMatch`, `RallyPoint`, `RallyShot`.
- **Tournament catalogue.** `GET /tournaments` and
  `GET /tournaments/{tournamentId}` (FREE): the stable id space
  `Match.tournament_id` joins, with `city`/`country` from a curated table and
  `category` only where the catalogues agree unambiguously — never derived
  from the name. New schema `Tournament`.
- **Rankings listing mode.** `GET /rankings` without `player` (PRO) returns
  the FULL published table in rank order for exactly one `system` — rows
  carry `player_name` as published and a null `player_id` outside our roster,
  so a top-N has no silent holes; `meta.coverage.effective_date` names the
  week served; `utr` has no listing. Per-player as-of records stay ULTRA.
  `RankingRecord` gains `player_name`, `previous_rank` (ATP/WTA) and
  `rank_movement` (ITF).
- **List filters.** `/matches` gains `player` (repeatable, max 50,
  either-participant), `country` (IOC-style lowercase 3-letter codes — NOT
  ISO-3166), `from`/`to` (UTC day boundaries, every status) and keeps `tour`;
  `/history/matches` gains `tour`, `player` and `country` alongside its
  existing `from`/`to`/`coverage`.
- **Match fields.** `Match` gains `tour` (the same vocabulary as the filter,
  null never guessed), `tournament_id`, `round_code` (controlled vocabulary
  `F`…`ER`, null when unrecognised), a documented `event_status` enum
  (`Retired` | `Cancelled` | `Walk Over` | `Postponed` | `Interrupted`, with
  the null-ambiguity caveat) and `withdrew` (1|2 on `Retired`/`Walk Over`,
  withdrawer = loser by rule); `winner` is now served for the full archive
  age.
- **Fixture fields.** `Fixture` gains `start_time` (null until the order of
  play assigns a time), `player1_id`/`player2_id` (exact-key roster
  resolution, never a name match) and `round_code`.
- **Tape additions.** Clean-sequence tape rows gain `point_winner` (derived
  from single-point transitions, never guessed; absent on raw); the tape
  detail gains a top-level `tiebreaks` array (observed terminal tiebreak
  scores per 7-6 set) and `meta.model_rows`; the history listing's `tape`
  object gains `model_rows`.
- **Archive bulk packages.** `/history/packages` and
  `/history/packages/{period}` gain `kind=archive` — the results archive
  (1968–2022) as YEARLY exports (`period` = `YYYY`), gzipped, alongside the
  monthly tape packages; the file manifest documents `compression`.
- **Statistics `final`.** The in-play statistics coverage vocabulary gains
  `final` — the closing figures of a completed match; a finished match cannot
  be "stale", so `age_seconds` is null there.

### Changed
- `info.version` is now `1.2.0`; `info.description` states the two history
  halves and the updated tier deltas (tournaments on FREE, the archive family
  and `/h2h` on BASIC/History plans, the rankings listing on PRO, rally and
  per-player as-of rankings on ULTRA).

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
