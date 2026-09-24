# Changelog

All notable changes to the specification are recorded here.

The API surface is versioned as `v1`. Changes within `v1` are **additive only**;
removing a field or changing its type would require `v2`.

## [1.13.45] - 2026-09-24
### Added
- **`GET /history/incidents` and `GET /history/incidents/{incidentId}/matches` are documented for the first time.** Both have been live and neither appeared anywhere in this reference, so the register a customer is meant to reconcile against could not be found from the documentation. `/history/incidents` returns the published data-quality incidents, oldest window first, each with its `window_utc` (start, end and the `basis` it was read from), `rule_before`, `rule_after`, `defect`, `affected_surfaces`, `how_to_tell`, `corrections` and `matches`. The register is part of a release and is not inferred at read time, so a record does not change between releases. `/history/incidents/{incidentId}/matches` streams one row per affected match as JSONL, or CSV with `?format=csv`, with the columns `incident_id`, `match_id`, `tournament`, `tour`, `round`, `draw_stage`, `scheduled_time`, `affected_field`, `served` and `expected`. A match whose derivation would be a guess is left out and the incident's `matches.note` says which, so the export is exact rather than complete. Measured on the live API 2026-09-24: five incidents across the kinds `pricing_rule`, `version_stamp`, `field_orientation` and `field_repair`.
- **The `verdict` object on the Score is documented.** Live since 2026-09-23 and absent from this reference. It is null on an ordinary read. When the legality gate refuses a state a stream has already published, it carries `kind` (`withdrawn`, `deferred` or `withheld`), `superseded_sequence` (the `sequence` a stream consumer is holding), `reason` and `safe_to_resume`, which is true exactly when `kind` is `withdrawn`. The push feed, the WebSocket and webhooks announce the same judgement as a `score_withdrawn` frame naming the same sequence, so a stream consumer learns a state was taken back without polling. `GET /matches/{matchId}/score` now names the field and points at the incident register.

No field, endpoint or behaviour changed by this release; both were already served.

## [1.13.44] - 2026-09-23

- **`GET /matches/{matchId}/points`: the row that closes a tiebreak set now carries `tiebreak_final`, and the reference did not say so.** Raised by a Pro customer running trading bots, who reported that the tape stops one point short of every tiebreak and that a field filling once a day was no use to a decision taken while the match is live. A tiebreak's last point is carried, like every set-winning point, by the set roll-up row (`tiebreak` false, the set banked 7-6, `score` 0-0), and that row never stated the breaker's score at closure. It now carries `tiebreak_final: [p1, p2]` in our player order, e.g. `[7, 5]`. Exact when the previous row is the decided score or one point from it, so it is derived from the stream itself and is present as soon as the set closes; otherwise taken from the match's recorded tiebreak finals, the same finals `GET /history/matches/{matchId}` publishes as `tiebreaks`; `null` when neither can state it, never guessed. Absent on every other row, including the breaker rows. A page that *starts* on a roll-up row has no previous row to read and uses the recorded finals alone. Measured at the endpoint over the 30 hours to 2026-09-23 20:30Z: 60 completed matches held 67 tiebreak sets and 36 of them served a closing score, only 7 of those matches having a recorded final at the time. Documentation of an already-served field; no behaviour changed by this release.

## [1.13.43] - 2026-09-23
### Fixed
- **The reference said a FREE key is refused the history endpoints outright. It is not, and has not been since 2026-08-07: a FREE key is served 20 history calls per calendar month.** Three separate statements carried the wrong rule — the FREE tier summary ("No historical results"), the `/matches` description ("requires BASIC ... and returns `403 upgrade_required` on a FREE key"), and the `status` parameter. Measured on the live API 2026-09-23 with a fresh FREE key: `GET /history/matches` answered `200` and kept answering until the monthly allowance was spent, after which it answered `403 upgrade_required` carrying `free_history_taste: "used"` and the detail "your 20 free history calls this month are used". A reader planning against the old text would have concluded the endpoints were closed to them and either bought a tier they did not yet need or abandoned the evaluation; a reader who tried anyway got a `200` the reference said was impossible and could not tell an allowance from a private grant. `/history/matches`, `/history/coverage`, `status=completed` on `/matches` and the FREE tier summary now all state the allowance and the refusal that follows it.

No field, endpoint or behaviour changed; every correction is to a description.

## [1.13.42] - 2026-09-23
### Fixed
- **Every per-point coverage count in this reference was measured in our own tables and published as though it described the API. It did not, and the gap is large.** `GET /matches/{id}/points` serves a COMPLETED match's stored per-point stream only while that stream passes our quality bar. Where it does not, the endpoint serves a measured-complete RECONSTRUCTION instead, and a reconstruction carries no clock and no `serve` / `outcome` tags at all. So the share of matches whose tags a reader can fetch is lower, sometimes far lower, than the share of matches a source tagged. Re-measured 2026-09-23 on what the endpoint publishes, beside what the previous text claimed: **Davis Cup World Group `serve` 2 of 22 (published as 22 of 22), World Group I 1 of 42 (published as 41 of 42)**; WTA qualifying `serve` **18 of 48** (published as 48 of 48); ATP Challenger qualifying `serve` **137 of 197** (195 of 197) and `outcome` **134 of 197** (191 of 197); WTA 125 qualifying `serve` **47 of 63** (61 of 63) and `outcome` **30 of 63** (24 of 63); ITF qualifying `outcome` **181 of 215** men's and **142 of 176** women's (189 of 209, 143 of 168); WTA main-tour qualifying `outcome` **5 of 48**, against 47 of 88 in the same events' main draws (published as 3 of 48 against 82 of 88). Both descriptions now state which layer they count and name `basis` as the per-response answer.
- `enrichment` per match was correct throughout, on every one of these matches, and `basis` has always named which sequence you were given. Only the prose was wrong.

No field, endpoint or behaviour changed; every correction is to a description.

## [1.13.41] - 2026-09-22
### Fixed
- **The `outcome` description named the wrong tour as the qualifying gap, and it was wrong in both directions.** It read "Qualifying draws follow their own tour, with one gap: ... Challenger (men) qualifying states no outcome at all." Measured 2026-09-22 over completed matches carrying a per-point stream since 2026-09-12, **ATP Challenger qualifying states `outcome` on 191 of 197 matches, with the full five-value vocabulary** (6,881 unforced errors, 4,275 winners, 4,267 forced errors, 1,026 aces, 774 double faults) — a reader who segregated a corpus on that sentence discarded the single richest qualifying population in the product. The gap is on the **WTA main tour**, which the old sentence implicitly cleared: WTA qualifying states `outcome` on **3 of 48**, against 82 of 88 in the same events' main draws. ITF qualifying is unchanged in direction (189 of 209 men's, 143 of 168 women's) and WTA 125 qualifying is partial (24 of 63). `enrichment` per match was correct on every one of these matches throughout — only the prose was wrong, and the prose is what a corpus is planned from.
- **`tour: challenger` pools two populations with different `outcome` coverage, and the reference described only one of them.** It read "Challenger: all five". That is true of ATP Challenger (`tier: challenger_50` … `challenger_175`): 252 of 255 completed main-draw matches with a stream carry the full five. It is not true of the WTA 125 events, which are also served as `tour: challenger` (`tier: wta_125`) and state **ace and double fault only** — 137 of 141 main-draw matches carry `outcome`, none of them a winner, forced error or unforced error. Read `tier`, not `tour`, to tell the two apart. Both descriptions now say so.
- **The `serve` qualifying denominators are re-measured** (WTA qualifying 48 of 48, ATP Challenger qualifying 195 of 197, WTA 125 qualifying 61 of 63) and name the populations by `tier` rather than by "Challenger (men)" / "Challenger (women)", which the served fields do not distinguish.

No field, endpoint or behaviour changed; every correction is to a description.

## [1.13.40] - 2026-09-22
### Added
- **`tier` and `tier_source` on every match and tournament object, with `?tier=` on `GET /matches` and `GET /history/matches`.** `tier` is the level the tournament was played at in the season of the match — the official category as the tour publishes it — and answers the question `category` cannot: is this a WTA 125, an ITF W35 or a Challenger 75? The vocabulary is closed: `grand_slam`; the ATP levels (`atp_finals`, `atp_1000`, `atp_500`, `atp_250`, `next_gen_finals`); the WTA levels (`wta_finals`, `wta_elite_trophy`, `wta_1000`, `wta_500`, `wta_250`, `wta_125`); `challenger_175` … `challenger_50`; the ITF World Tennis Tour categories (`itf_m15`, `itf_m25`, `itf_w15` … `itf_w100`, with the 2023 women's categories kept as printed that season); the team events (`united_cup`, `davis_cup`, `bjk_cup`, `laver_cup`, `olympics`); `juniors`; `utr`; `exhibition`; or `null` — nothing we hold names the level, never guessed. The tier is per season and it moves under one `tournament_id`: Dallas was `atp_250` in 2023 and 2024 and `atp_500` from 2025, so a 2024 Dallas match reads `atp_250` and a 2025 one `atp_500` under the same id. A match's tier is resolved by the calendar year of its `scheduled_time`, never copied from the tournament row; `/tournaments` rows carry the current season's, null when this season's calendar does not list the event. `tier_source` says how the level was established — `calendar` (the official per-season tour calendar), `name` (an unambiguous name rule: the ITF category is in the event's official name, team and UTR events are named as such), `wikipedia` (the season's schedule page, only where the official calendar could not state the level for that season), `resolver` (resolved after the seed dataset by the same rules) — and is null exactly when `tier` is null. The 2023–2026 seasons were verified event by event against the official calendars (99.1% of tournament-seasons resolved; the rest deliberately null). `?tier=` takes comma-separated exact values, read from the same per-season table so filter and field cannot disagree; a null tier matches no value; an unknown value is a `400 bad_tier` with the offending values in `bad` and the full vocabulary in `allowed`. `category` is unchanged and remains the coarse class.
- **A correction to a published result is signalled, never a silent edit: `basis: restatement` on the status history, `result_restated_at` / `result_version` on every match object, and `?restated_since=` on `GET /history/matches`.** Raised by a licensed results customer settling off our results. Once a match has been published as `completed` (or as a cancelled walkover with a winner), any later change to `status`, `event_status`, `winner` or the final score is appended to `GET /matches/{matchId}/status-history` as a new row with `basis: restatement`, at the instant we made the change: `status` / `event_status` carry before and after as usual (the same value twice when only the winner or the score moved) and `score` is the result after the correction. This holds for every path that can change a result — a source's late final, a second authority's correction, an operator's repair, a completion reopened and re-closed — because it is enforced where the result is written, not by each path remembering to say so; a re-assertion of the same result, or a change to points alone, writes nothing. `result_restated_at` is the instant of the newest such row (null while the result stands as first published); `result_version` is `1` plus the number of corrections — record it with the result you settle on, and a higher number on re-read means the one you hold was superseded. `?restated_since=<ISO instant>` keeps only the matches corrected after that instant — the poll to run after each settlement pass; a `Z` or an offset, a naive value read as UTC, and a bare date refused as `400 bad_restated_since`, because a day is not an instant. Rows with this basis exist from 2026-09-22; earlier corrections were not signalled and nothing is reconstructed for them.
- **`winner` on every row of every history tape: who won the point that produced the row.** Raised by a modelling customer initialising serve states from the tape — `server` and `serve` were stated per row, and the third fact a model needs was only implicit in the score step. `winner` (`1` | `2` | null) is judged from the score step between the row and the previous served row (the previous raw row on the raw sequence, the previous clean row under `?sequence=clean`), by the same rule the completeness ledger counts a legal transition with — and from nothing else: never the serve, the server, the outcome tag or the pattern of play. Null on the first row and wherever the step is not one attributable point: a re-sent row, a set opener, a backward correction, a multi-game jump. A step whose games total rises by exactly one attributes to the side whose count rose — the game point was theirs — whatever in-game points the step skipped, a missed poll or a game withheld whole (`meta.points.games_withheld`). Present on the raw and clean sequences, on `?points=complete` reads and on the pre-2023 archive tape; equal to `point_winner` wherever that older key is present, which is kept unchanged for existing readers. Derived once per response, never stored.
- **`schema_version` on the packages listing, and bulk tape rows carry the enriched tape.** Under `schema_version` 2 a `kind=tape` JSONL line is exactly what `GET /history/matches/{matchId}` returns for that match on its default basis, produced by the same code — the same rows with `origin`, `serve`, `outcome` and `winner` beside the score columns, and the full `meta` (`enrichment`, `reconstructed_at`, `observed_span`, `meta.points` where served) — so a model reads its serve states from the bulk file just as it would from the endpoint; the CSV appends `origin`, `serve`, `outcome`, `winner` after `danger`, in that order, and its column order grows only at the end. `1` is the shape every month built before 22 September 2026 carries: score columns only, no `meta.enrichment`, and a CSV that ends at `danger`. Months built before that date keep shape `1` until they are rebuilt — newest month first, then backwards, `built_at` and `sha256` moving as each flips — so check the manifest rather than assuming; a consumer that needs the enriched fields should require `schema_version >= 2` and, for a month still at `1`, read the per-match endpoint for the matches it needs. `null` on the non-tape kinds.

### Changed
- **A completed match on the tours whose own point-by-point console we read is re-joined after the match against the console's complete sequence.** ATP 250/500/1000, ATP Challenger and WTA 1000/500/250/125: the live join paired `serve` / `outcome` onto points as they were captured, so a point the console published after our capture went untagged. A completed match is now re-joined against the complete console sequence by the same exact-state rule, and its serve/outcome coverage exceeds what was captured live. The late tags arrive as `point_update` frames and `tagged_at` revisions like any other — collect them with `?changed_since=`. Nothing is inferred; a point the console never states stays null.
- **The pre-2023 archive tape no longer claims `point_winner` is null throughout a per-game tape.** On a per-game tape (556 matches, 555 of them 2013) consecutive rows differ by a whole game, and the reference said no point was attributable there. Each row in fact reads the side whose game count rose — the game point was theirs — and says nothing about the game's other points; `winner` reads the same. No field changed shape or value.

## [1.13.39] - 2026-09-22
### Changed
- **`is_qualifying` states the one case where a round label DOES decide the draw.** The field said it is "never inferred from the round label", which is the right instinct and slightly too strong: main-draw vocabulary (`Semi-finals`, `Final`) is indeed never read that way, but a round the feed itself spells `Qualification Round 1` is the source STATING the draw, and it reads `true` — a `false` beside such a round is a payload contradicting itself rather than asserting main draw. Three matches (Chengdu, 22 Sep) were briefly served `is_qualifying: false` with `round_code: "Q1"` beside them and were repaired the same morning. Readers segregating a corpus by draw need to know which way that conflict resolves. No field changed shape or type.

## [1.13.38] - 2026-09-22
### Changed
- **`GET /markets` states that the scope is MATCH-WINNER ONLY, and returns at most one market.** A prospect asked whether the odds endpoints carry game spreads / handicaps (`A -3.5 @ 1.90`) in addition to match-winner prices. Every description in this reference already said "match-winner market", but nowhere said what that EXCLUDES, and the endpoint's own summary said "market(s)". Both are now explicit: no handicaps or game spreads, no totals, no set-winner books, no per-game or per-set derivative; `data` holds at most one object and `meta.count` is 0 when nothing is mapped. Venues do list tennis derivatives beside the match-winner book and this API publishes none of them — a derivative is refused at the mapping step. No field changed shape or value.

## [1.13.37] - 2026-09-21
### Added
- **`is_qualifying` is documented on the match object.** The field has been served on `GET /matches`, `GET /matches/{matchId}` and `GET /history/matches` for some time and was absent from this reference entirely, which left the one field that separates a qualifying draw from the main draw invisible to anyone reading the docs. Three-valued: `true`/`false` are the source's own assertion, `null` means no source has ever stated it, and `null` is not `false`.

### Changed
- **`round` and `round_code` now state that they are DRAW-RELATIVE.** Both describe the round *within* the draw the match belongs to, and the draw is named by `is_qualifying` — not by the round. A qualifying semi-final carries `round: "... - Semi-finals"` and `round_code: SF`, exactly as a main-draw semi-final does; `Q`/`Q1`..`Q4` appear only where the feed itself names the round as qualifying, which most feeds do not. `round_code` previously said "this is the field to branch on" without that limit, and two customers independently read a qualifying match as a main-draw one and reported it as a data fault. The data was correct in every case; the documentation was not. No field changed shape or value.

## [1.13.36] - 2026-09-21
### Changed
- **`GET /charting/players` states a sample of 11,803 charted matches, not 11,646.** The charted corpus was refreshed on 2026-09-19 and 184 matches — 133 of them played after 2026-05-24, including the US Open women's draw to the quarter-finals — were loaded into the product on 2026-09-21. `matches_charted` on every response has always been the true per-player denominator and was never affected; the curated-coverage note beside it was quoting an older total and understating the sample. `GET /rally/matches` grew in the same load: 11,822 charted matches and 1,875,132 shot-by-shot points, with the newest women's chart now 2026-09-09. The men's corpus is unchanged because nothing has been charted upstream since 2026-05-21. No field changed shape.

## [1.13.35] - 2026-09-21
### Added
- **`meta.points.games_short` on `GET /history/matches/{matchId}` counts the completed games the tape holds too few points for.** Raised by a prospect evaluating per-point histories. A game the tape skips whole is a legal `0-0 → 0-0` boundary with the games counter up by one, and the transition test alone cannot see it — so a tape could read `complete: true` with a whole game missing. The measurement now walks the sequence by game boundary and compares what is held for each completed game with the fewest points that game can have contained given the last state it shows (from 0-0 at least 4; from 15-30 at least 5; from 40-40 at least 8; a tiebreak at least 7) — a lower bound, never an estimate. A game the tape skips whole counts; so does a game that ended with no further rows after its last stored point. `> 0` forces `complete` to `false`; nothing is inferred or repaired, and the game's boundary rows are still served exactly as stored. `null` = nothing measured (an empty sequence).
- **`basis_reason` on `GET /matches/{matchId}/points` says why a reconstruction was served instead of the stream.** Present on the `reconstruction` basis only: `stream_absent` (no stored stream rows), `stream_incomplete` (the stream is legal but does not measure complete — it joined mid-match or stopped short — and carries no tags) or `stream_illegal` (at least one transition is not attributable to one point: a gap or a torn row). A stream that is complete, or tagged and legal end to end, is always served on the `live` basis and the key is absent. Additive; nothing else in the response changes shape.

### Changed
- **`meta.points.complete` now means the served sequence holds at least every point the score requires — not merely that consecutive rows are consistent with each other.** True only when the sequence opens at 0-0, every transition is a legal single-point step, it carries at least as many point transitions as the final scoreline implies the match contained, every completed game holds at least as many point transitions as it must have contained (`games_short` is `0`), it reaches a finished final scoreline at love (or the match ended early — retirement/walkover), it is not known-truncated, and no game was withheld (`games_withheld`). `ends_at_final` on the same object now also requires that the last row shows no game in progress — points at love or null, not a tiebreak in progress: a row carrying a finished spine with a game still underway (`[[6,6],[3,4]]` at 15-0) reads `false`, where before the spine alone decided. Some tapes that read `complete: true` until now will read `false`; no row is changed.
- **A recurring score state on the history tape pairs its `serve`/`outcome` by nearest clock, instead of reading null.** Tags on `GET /history/matches/{matchId}` rows are joined from the match's per-point stream by exact score state, and a state the stream asserts more than once (a deuce cycle revisiting deuce) cannot be told apart by the score, so until now it read `null` outright. Where a state recurs the join now pairs by nearest clock within 90 seconds — the tape row's observed clock against the stream point's, each stream point used at most once — and reads `null` otherwise (no candidate within the window, or two at the same distance). Every tag is an observed pairing, state and where needed clock, never an inference from the pattern of play. Reconstructed rows and rows no stream point matches still read `null`.

### Fixed
- **A stored live stream that is complete, or tagged and legal end to end, is served on a completed match; a reconstruction is projected only when the stream falls short.** Until now a measured-complete recorded sequence displaced the stream unconditionally, so a completed match could lose its `serve`/`outcome` tags and every per-point clock the moment a reconstruction landed — a projection carries neither, so a complete tagged stream is strictly more information than any reconstruction of the same match. `GET /matches/{matchId}/points` now keeps the `live` basis whenever the stream is itself measured complete (match-closing point included) or carries tags and is legal end to end (every transition one attributable point, judged in playing order), and serves the projection only when the stream has no rows, is incomplete and untagged, or holds a transition nobody can attribute — `basis_reason` says which. When the reconstruction serves it still serves wholesale; the two sequences are never interleaved. If a completed match reads `reconstruction`, re-read from `after_seq=0` rather than resuming a live cursor into it.
- **A double fault stated on a first serve is a contradiction; the point is served untagged.** A source point whose serve number and outcome contradict each other — a double fault on serve 1 — was carried through as stated. `serve` and `outcome` on such a point now both read `null` on `GET /matches/{matchId}/points` and on the WebSocket frames rather than tagged wrongly; nothing is corrected to a second serve. Stored tags that carried the contradiction have been cleared.
## [1.13.34] - 2026-09-21
### Changed
- **The reference said Davis Cup and the Grand Slams "read null throughout" for the per-point tags; `serve` is in fact stated on the top Davis Cup tiers.** `serve` and `outcome` are joined from *different* outside sources, and the old sentence excluded both on the strength of one of them: the tour's own per-point console does not carry team ties or Slams, so `outcome` is genuinely `null` there — but the source that states the serve number does carry them. Measured over completed matches with a per-point stream since 2026-09-12: Davis Cup World Group states `serve` on 22 of 22 matches and World Group I on 41 of 42, while World Group II states it on 0 of 38; `outcome` is null on all of them, on every one of the 14,132 rows. The machine-readable authority was right throughout and is unchanged — a World Group I match answers `enrichment: {"serve": "stated", "outcome": "none"}` and a World Group II match answers `{"serve": "none", "outcome": "none"}` — so this corrects the prose to match what the API already returns, in the direction of more coverage, not less. The `serve` description now names the Davis Cup tiers in its coverage list with the measurement; the `outcome` description now separates the two sources instead of excluding a competition from both. No field, endpoint or behaviour change.

## [1.13.33] - 2026-09-21
### Changed
- **`serve` and `outcome` said nothing about qualifying or doubles draws, and the internal reference called both blanket-`null`.** The per-point tags (added 2026-09-12) were documented tour by tour for main draws only. Measured over completed matches carrying a per-point stream since the source went live on 2026-09-12: WTA qualifying states `serve` on 48 of 48, Challenger (men) qualifying on 153 of 155, Challenger (women) on 49 of 51; ITF qualifying states `outcome` (aces and double faults) on 95 of 107 men's and 62 of 74 women's. Qualifying draws are covered like their own main draw, with exactly one real gap — `outcome` on Challenger (men) qualifying, which no source states at all. The doubles half of the old claim is confirmed and now carries its denominator: across 454 completed doubles matches in the same window, not one row carries either field. Both descriptions now state where each field is stated, including the qualifying and doubles positions; `enrichment` per match remains the authority and none of it is a promise about a match not yet played. Found by the every-sweep tag-coverage check, which reads 85 of 86 Challenger qualifying matches carrying `serve` against a documented `null`. No field, endpoint or behaviour change.

## [1.13.32] - 2026-09-21
### Changed
- **A match that ends in a tiebreak closes with the set roll-up row after the decisive tiebreak score.** The match-closing row on `GET /matches/{matchId}/points` was described as if the last point were always a game point one point short of the final, and a match decided in a tiebreak did not fit that shape. The docs now say what the stream actually holds: when a completed match ends in a tiebreak, the stream's last stored row is the decisive tiebreak score itself (7-3, or 8-6) and the closing row is the set roll-up after it — the next game number, `number` 0, `tiebreak` false, `sets` incremented for the tiebreak winner, the set banked 7-6 in `games`, `score` 0-0, `server` null, `winner` the tiebreak winner — the same row the stream stores after every other set-ending tiebreak, so `ends_at_final` reads `true` there. A 10-point match tiebreak still cannot be stated as one point and is refused as before (`ends_at_final: false`), as is a tape that never reached the final.

## [1.13.31] - 2026-09-20
### Added
- **`GET /matches/{matchId}/points` now closes a completed match with the match-closing point, and `ends_at_final` says whether it did.** Raised by a prospect evaluating per-point tapes, who asked where the point that wins the match is. Every row is the state *after* a point, so a game-winning point is carried by the next game's `number: 0` opener — and the match-winning point had no next row to be carried by: the live stream never held it, and a serve statistic built off the stream was missing every match's last point. On a completed match served on the `live` basis the page now ends with one terminal row: `seq` = last + 1, `number` 0, `sets` / `games` the final score, `score` 0-0, `tiebreak` false, `server` null (nobody serves next), `winner` the match winner, `ts` the instant the final score was observed. It is built at read time from the stream's last row and the observed final score, and only when the two are one point apart; nothing is fabricated otherwise. `ends_at_final` (boolean) on the response says whether the sequence served ends on that row: `false` on a completed match whose stream stops short of it (a retirement or walkover, a capture that stopped two or more points short, a closer from deuce or from a match tiebreak that cannot be stated as one point), always `false` on a live match, and on the `reconstruction` basis judged from the projected sequence's last frame. `serve` / `outcome` on the terminal row are null: no source's tag for a match's last point is stored yet. WebSocket and push frames are unchanged.
- **`tagged_at` on every point row, and `?changed_since=` on the same endpoint, so late serve/outcome tags are collectable without a socket.** The same prospect asked how to pick up tags that land after a row was read. `after_seq` is a cursor by `seq`, so it can never return a row already held — and a `serve` / `outcome` tag that lands late lands on exactly such a row; until now the only way to see it was the `point_update` frame on a WebSocket. Every row now carries `tagged_at`, the UTC instant its tags landed (null while none has, and on every `reconstruction`-basis frame), and `?changed_since=<ISO-8601 instant>` (`2026-09-20T00:35:18Z`; `Z` or an offset, a naive value is read as UTC, a date alone is refused) returns only the rows whose `ts` **or** `tagged_at` is later than that instant, in `seq` order, paged as usual and composable with `after_seq`. The post-match recipe: read the match, keep the instant, re-read with `changed_since=<that instant>` and replace held rows by `seq`. Anything that is not an ISO-8601 timestamp is a `400 bad_changed_since`. On the `reconstruction` basis no row carries a clock or a tag, so a `changed_since` read of it is an empty page: that sequence is final at first read.

## [1.13.30] - 2026-09-20
### Changed
- **The ATP per-point outcome row said "full" as a projection from the feed's content, not a measurement.** In the 30 days since the tour's own per-point console went live (2026-09-12), no ATP main-tour event was actually played — the only tour tennis in that window was a Grand Slam and Davis Cup, neither of which is on that feed — so every ATP main-tour match carried no outcome tags at all, while the docs asserted `full` (ace, double fault, winner, forced error, unforced error) unconditionally. The row now names the tours the feed covers (ATP 250 / 500 / 1000), states plainly that Grand Slams and Davis Cup are not on it and read null throughout (check `enrichment` per match), and gives the first date the claim was actually measured against a played tour event: the week of 2026-09-22.

## [1.13.29] - 2026-09-20
### Changed
- **The `GET /history/matches` listing's point-completeness ledger now judges the same raw sequence the per-match read serves, re-sent rows dropped — not the `clean` collapse.** The ledger's previous default basis, `clean`, collapses the tape to one row per distinct score state; that collapse can delete a real deuce point — two rows sitting at 40-40 with no advantage row between them is a legitimate rally, not a duplicate — and call the resulting, shorter tape point-complete when the tape actually served is not. The ledger now judges the raw sequence with provable re-sends dropped, the exact judgement the per-match read makes and publishes as `meta.points.complete`, so `tape.points_complete_default` on the listing and `meta.points.complete` on a fetched match agree by construction instead of disagreeing on a sequence the read never served. Measured on 7,717 completed matches scored since 1 Sep: the `clean` collapse called 70 of them point-complete whose served (raw) tape was not, and missed 810 whose served tape was. `clean` remains available only as a request option (`?sequence=clean`); rows scored before 2026-09-20 keep `points_basis: clean` until the nightly re-score reaches them. `tape.points_basis`, `tape.points_complete_default` and `tape.points_complete` descriptions updated to match.
### Fixed
- **`tape.computed_at` on the `GET /history/matches` listing carried the serving host's UTC offset (`+03:00` on prod) instead of a trailing `Z`.** Same instant, valid ISO-8601, but every other timestamp in the payload — `meta.generated_at`, each row's `timestamp` — ends in `Z`, so a consumer diffing `computed_at` against either had to normalise it by hand first. Now projected to UTC with a trailing `Z` like the rest of the surface.

## [1.13.28] - 2026-09-20
### Added
- **`meta.points.games_withheld` on `GET /history/matches/{matchId}`.** Present whenever reconstructed rows are in the response: the count of games whose vendor point record was internally inconsistent — a recorded score state that repeats or moves backwards partway through the game — and whose in-game points are therefore withheld rather than published. The game's opening `0-0` row is still served, so the games spine stays intact; nothing is repaired, reordered or inferred — a game is served exactly as recorded, or not at all. `> 0` forces `meta.points.complete` to `false`. `null` means not measured: either the reconstruction predates this check, or it was built from the multi-vendor union rather than a single vendor's point record.
- **`tape.points_complete_default`, `tape.points_complete_recon` and `tape.points_basis` on the `GET /history/matches` listing.** `points_complete` on that listing is a best-basis OR: the ledger's default basis is the `clean` collapse of an observed tape, while the per-match read serves and measures the `raw` sequence, so `points_complete: true` can sit next to `meta.points.complete: false` on the same match with both honest about their own sequence. These three fields say which measurement produced the `true` and on which sequence — `points_complete_recon: true` means "fetch it with `?points=complete`". All null when not yet measured.
- **`meta.points.resent_rows` on `GET /history/matches/{matchId}`.** A row identical to the row before it is the same state re-sent by a source on its timer, which the raw tape carries by design — no point separates the two rows, so they no longer count as a non-point transition. `transitions_total` is now `rows − 1 − resent_rows`. `resent_rows` is `0` on a `clean` or `recon` basis: the collapse already removes re-sends, and in a reconstruction one row is one point, so a repeat there is a vendor tear and is never dropped.
### Fixed
- **A vendor's finished-match point record that moved backwards inside a game was being reconstructed as if it were legal.** Since July 2026 one vendor's point-by-point feed has not been monotone within a game (a real example: 40-30, 15-15, 15-30, 30-30, 15-30, 30-30, 30-30, 40-30 — 547 of 586 August ATP/WTA matches carried at least one such game). The tape builder kept the longest forward-moving chain through the inconsistency and published the result as an ordinary reconstructed row, so a state like 30-30 repeating three times in a row was served as fact. Those games are now withheld whole instead — counted in the new `games_withheld` field — rather than fitted into a plausible-looking sequence.

## [1.13.27] - 2026-09-20
### Added
- **`GET /history/matches/{matchId}` tape rows now carry `origin`, and observed rows carry `serve` / `outcome`.** Raised by a prospect evaluating reconstructed tapes as evidence for an independent model, who asked how to tell observed from reconstructed rows explicitly, when a reconstruction landed, and whether the per-point serve/outcome tags reach the history tape at all. `origin` (`observed` | `reconstructed`) is read from the row's stored provenance — the same fact that nulls the clock on a reconstructed row, never the null clock itself — so a caller no longer has to treat `timestamp: null` as an inferred marker. `serve` (`1` | `2` | null) and `outcome` (`ace` | `double_fault` | `winner` | `forced_error` | `unforced_error` | null) are joined onto **observed rows only** from the per-point stream by EXACT score state: set count, every set's games, in-game points and the tiebreak flag all equal. A tape row stores no point ordinal, so a score state the stream asserts more than once (a deuce cycle revisiting deuce) is ambiguous and reads null, as does a row no stream point matches and every `reconstructed` row — nothing is inferred from the score. All additive on `GET /history/matches/{matchId}`; the pre-2023 `ArchiveTape` (every row reconstructed) does not carry `origin`, `serve` or `outcome`.
- **`meta.reconstructed_at`, `meta.observed_span` and `meta.enrichment`** on the same endpoint. `reconstructed_at` is the write time (UTC) of the newest reconstructed row actually served, null when none is; `observed_span` is `{"first", "last"}` — the `timestamp` of the first and last observed rows served, in served order, null when none is; `enrichment` is `{"serve": "stated" | "none", "outcome": "full" | "ace_double_fault" | "none"}`, the vocabulary that actually landed on this response's rows (`none`/`none` on a wholly reconstructed tape). All three are measured on the rows returned, after any `sequence=clean` collapse.
### Changed
- **`meta.points.available_complete` is now read-through instead of nightly-only.** It still answers from the nightly ledger when the ledger has an entry. When the ledger has none yet — a reconstruction that landed after the last nightly run — and this read served a reconstruction, it now answers from the live verdict just measured on that reconstruction instead of `null`. It reads `null` only when there is no ledger entry and nothing was reconstructed on this read to measure. No field or endpoint added; behaviour change on an existing field.

## [1.13.26] - 2026-09-20
### Fixed
- **Team-competition matches now carry the surface of their tie.** Davis Cup, Billie Jean King Cup and Laver Cup matches published `surface: null` on the match and on `tournament.surface` — 268 of 268 team-event matches in the 60 days to 2026-09-20. 1.13.25 documented that null as structural; it was only structural for the sources we had. Every surface source was per tournament, and the vendor's team "tournament" (`ATP Davis Cup - World Group I`) is a tier whose surface field carries the draw stage, not a surface; a tie is played on whatever its host nation chose. The ITF's own draw feed states the surface, venue and indoor/outdoor flag per tie, so the API now holds one row per tie and resolves each match to its tie by competition, date window and the nations on court — answering only when a single tie remains, never from a nation, a name or a previous tie. Existing team-event matches (last 60 days and upcoming) were backfilled with one audit row per write; new ties are picked up as they are drawn. Ties whose venue the ITF has not announced stay null. `tournament.surface` for a team competition remains null by design: the surface belongs to the tie, and it is published on the match. Raised by a public report that Davis Cup match 191867 returned `surface: null`; that match now serves `hard`. Payload shape unchanged.
### Changed
- **`Match.surface` and `Tournament.surface` descriptions** now state the per-tie rule for team competitions instead of describing the null as permanent.

## [1.13.25] - 2026-09-20
### Fixed
- **A match that had been given a `tournament_id` was never given the surface that id serves.** `matches.tournament_key` was backfilled on 2026-09-04 for matches discovered through the secondary source, which had been publishing `tournament_id: null`; the pass gave those rows an id and stopped there. The catalogue-surface fallback runs only in the ingest upsert, and every repaired row was already terminal, so it never ran again: 2,533 matches (2026-06-21..2026-09-04, all ITF) published `surface: null` while `GET /tournaments/{id}` — for the id that same row hands you — answered `"surface": "hard"`. Two surfaces for one question, each written by a different writer. Measured and wire-confirmed before the repair on match `186637` (`surface: null`, `tournament_id: "12158"`) against `/tournaments/12158` (`"surface": "hard"`), and after it on the same row. All 2,533 now carry the surface their own tournament states; `indoor` was filled from the same catalogue row where the match held none. Nothing after 2026-09-04 was affected — the same commit's ingest hook sets the key before the fallback reads it, so the forward path has been correct throughout and the weekly count is flat zero since. The repair resolves surface through the same chain the ingest uses (tournament-name map first, catalogue second), so a later upsert cannot answer one of these rows differently. Match-level `surface` null over the previous 90 days: 19.8% before, 11.8% after. No field or endpoint added.
### Changed
- **`Match.surface` and `Tournament.surface` now say when they are null and why.** Both were documented as nullable with no account of the population, while the `tournament_id` field beside them carries a measured one. The remaining match-level nulls are two structural groups and an 8-row residue: UTR events, which are not in the tournament catalogue at all (and so publish `tournament_id: null` too), and TEAM COMPETITIONS — Davis Cup, Billie Jean King Cup, Laver Cup — where the surface is the host nation's choice per tie, so neither the season-long tournament row nor the match has one to state. Raised by a public report that Davis Cup matches return `surface: null`. For those 35 catalogue rows the upstream surface field carries the draw tier ("- Preliminary", "- Play Offs", "- Promotion") rather than a surface, and a value outside hard/clay/grass is rejected rather than published. No behaviour change.

## [1.13.24] - 2026-09-20
### Changed
- `GET /matches/{matchId}/score` no longer answers 404 for a settled match whose live-score rows were retired by the 90-day retention sweep, or that only ever had an archived final. When there is no live row at all, a match with a non-null `outcome` (completed, retired, walkover, default, abandoned, unresolved) is answered from its archived final — the same read `GET /matches?status=completed` already embeds, through the same serializer — so the listing and the single-match read can no longer disagree about whether a score exists. Unchanged: a live match always reads its live tape (the archive never outranks it); an upcoming match with no row, a cancelled match that was never played, and a settled match with nothing recorded anywhere still answer 404. An archived final carries `age_seconds`, `observed_age_seconds`, `sources_count` and `accepted_at` as null — no clock is claimed for a state nobody watched — and `timestamp` null where the archived row has none; the Score object still carries no data-source label, `GET /history/matches/{matchId}` `meta.point_source` says whether the final was observed or reconstructed. Behaviour change on the API side 2026-09-20; measured at the change: 13,437 completed matches from the previous 180 days, 157,170 all time, now answer `/score` instead of 404. No field or endpoint added.

## [1.13.23] - 2026-09-20
### Fixed
- **`GET /rankings` accepted `?surface=`, `?min_matches=`, `?activity_weeks=` and a contradicting `?tour=` on the official systems, and silently ignored all four.** Measured on production before the fix: `?system=atp&surface=clay`, `?system=atp&min_matches=200`, `?system=atp&activity_weeks=4` and `?system=atp&tour=wta` each returned `200` and the plain overall ATP table, byte-identical to the same call with no parameter at all; `?system=atp&tour=zzz` was accepted too. All four are documented "Elo only" / "Elo listing" and are read nowhere else, so a caller asking for a clay ATP leaderboard received the overall one with nothing in the response to say the filter had not run. The `elo` branch was correct throughout and is the control that makes this a defect rather than an empty population - `?system=elo&tour=atp&surface=clay` returns a genuinely different top 10 from `surface=hard`, and `surface=zzz` is refused with the valid list. Unlike the `has_market` hole fixed in 1.13.21, this one cannot be closed by making the filter act: there is no clay ATP ranking and no WTA row in an ATP table. `surface`, `min_matches` and `activity_weeks` are now a `400` when no requested system is `elo` (a mixed `?system=atp&system=elo&surface=clay` still passes); `tour` is a `400` only when it contradicts a system the caller NAMED, or when that system is not an ATP/WTA walk. `?system=atp&tour=atp` is redundant rather than wrong and still answers, and the implicit default system set is unchanged.

## [1.13.22] - 2026-09-20
### Added
- **`GET /history/archive/players` now takes `?id=` (alias `?player_id=`), so the corpus person id we publish can finally be looked up.** Archive match rows have published that id as `winner.player_id` / `loser.player_id` since 2026-08-03, and this endpoint has published it as `id` and described it in those words — but the only surface accepting the value was `/rankings?archive_player=` — ULTRA, `system=elo` only, and it answers with RATINGS, not the person. So the PERSON could not be reached by id at all: a reader holding a corpus id could only go back to the NAME. It is a filter on the list rather than a `/history/archive/players/{id}` detail route on purpose: the natural key is `(tour, source_pid)`, the two tours number independently, and 14,627 corpus person ids are live in BOTH (measured 2026-09-20) — a detail route would have to pick a tour and would return the wrong human for those ids without saying so. The list returns every person wearing the id; add `tour` to narrow it to exactly one. Sending `id` and `player_id` with different values is a `400`.
### Fixed
- **A corpus person id sent to `GET /players/{playerId}` returned a bare `404` that explained nothing.** The roster (`/players`, ids 1-37033) and the results-archive person registry (100001-270580) are separate, deliberately disjoint id spaces - 0 of 137,483 corpus ids resolve on `/players/{playerId}` - and the only id-shaped route with `player` in its name was the roster one. The `404` now carries `detail` and a `see` pointer at `/history/archive/players?id=...` when the id resolves in the archive registry; an id from neither space keeps the plain body. The same signpost is on `/players/{playerId}/stoppages` and `/players/{playerId}/injuries`. The status is deliberately still `404` and not `410`: `410` asserts the id once existed HERE, and it never did. The person is never named in the `404` - the archive is History-gated and `/players/{playerId}` is not.
- **`GET /players/{playerId}` was missing its `410` in this specification.** The route has answered `410 PlayerMerged` with a forwarding address for a merged or retired player id for as long as its two stoppage aliases have, and both aliases documented it while the main detail endpoint did not. Now documented, along with a `PlayerNotFound` schema that states exactly when `detail` and `see` are present.

## [1.13.21] - 2026-09-20
### Fixed
- **`GET /matches` accepted `?has_market=` and silently ignored it, and `status=cancelled` ignored `?has_analysis=` as well.** The filter was implemented in the shared query builder on 2026-09-15 and exposed on `/history/matches` the same day, but it was never wired to `/matches`: every row published `has_market`, the query string was accepted, and the unfiltered page came back under a `200`. Measured on production before the fix — `status=live` returned the same 14 rows (2 with a market) for `has_market=true`, `has_market=false` and no filter at all; `status=completed` the same 100 rows (38 with a market); `/history/matches` was correct throughout (40/40 and 0/40). Five of the eight status x filter combinations returned a wrong answer under a success code. Both filters now apply on every status, and an unparseable value is a `400 bad_has_market` / `bad_has_analysis` as documented.
### Added
- `has_analysis` and `has_market` are now DOCUMENTED as query parameters on `GET /matches`. `has_analysis` has worked on `live`, `upcoming` and `completed` since 2026-09-14 and `has_market` works everywhere from today, but neither appeared in this specification, so the only filter a reader could find was `has_market` on `/history/matches`. The prose telling callers to "filter the slate first" was therefore advice with no documented instrument behind it.

## [1.13.20] - 2026-09-19
### Fixed
- **The two win-probability regime boundaries published in 1.13.19 were three hours late, and are corrected here: 2026-08-18T08:29:28Z and 2026-09-16T07:59:54Z.** Both switch instants were read off `config.updated_at`, a column this application stores in **naive local wall time (UTC+3)**, and were published as if they were UTC. Verified six independent ways on 2026-09-19: six config rows whose own value is an epoch each read exactly +3 h against their `updated_at` (e.g. `monitoring.worker_heartbeat_ts` = 2026-09-19T20:22:46.465Z stored as `23:22:46.467`). The corrected instants are the config switches themselves — `win_probability.match_tiebreak_detection_enabled` at 2026-08-18 08:29:28.93Z and `win_probability.itf_pricing_draw_rule_enabled` at 2026-09-16 07:59:54.76Z — which is the earliest instant from which a state can carry the new rule, and therefore the safe place to cut.
- With it, the measured lag of the version string: the `+itfdraw-2026-09-16` suffix first appears on rows generated 2026-09-17T05:04:25Z, which is **21 h 04 m** after the rule landed, not 18 h 02 m. That figure had been derived from the same three-hour-late instant. `2026-09-17T05:04:25Z` and `2026-09-12T12:08:17Z` were both taken from `win_probability_meta.generated_at`, a timezone-aware column, and are unchanged and correct.
- Anyone who segregated a corpus on 2026-08-18T11:29:28Z or 2026-09-16T11:02:00Z should re-cut: the three hours before each corrected instant are on the wrong side of the split.

## [1.13.19] - 2026-09-19
### Changed
- `Score.win_probability_meta`: the two win-probability **regime boundaries** are published here for the first time, so a customer can segregate a recorded corpus without asking us. Two changes moved published live probabilities before `model_version` reflected them — 2026-08-18T11:29:28Z, when the over-inclusive deciding-set rule for lower-tier singles began, and 2026-09-16T11:02:00Z, when the draw-based rule replaced it (BOTH INSTANTS WERE THREE HOURS LATE AND ARE CORRECTED IN 1.13.20 — use 08:29:28Z and 07:59:54Z) (up to 0.20 on affected deciding-set states) — so the cut is on `generated_at`/`timestamp`, never on the version string. Published in the application's internal reference on 2026-09-17 and not ported here until now; docs.livetennisapi.com, which is the artifact a customer opens, carried none of it.
- The same description states, newly measured, that `model_version` is **not** a safe discriminator across the second boundary: the `+itfdraw-2026-09-16` suffix first appears on rows generated 2026-09-17T05:04:25Z, 18 h 02 m after the rule landed (corrected to 21 h 04 m in 1.13.20). Measured against production on 2026-09-19: in that gap 33,510 states across 351 matches — 9,719 states over 113 matches at the ITF M15/W15/W35 levels the rule governs — were computed under the corrected rule while still carrying `markov-population-2026-08-23`. A cut on a whole-day boundary mislabels exactly those rows; a cut at the 11:02:00Z instant does not. The previous internal wording ("timestamp only up to 2026-09-17") was right to the day and vague by eighteen hours.
- `Score.win_probability_meta.model_version` now carries a description of its own, and the pre-stamp caveat is stated with its instant: no row generated before 2026-09-12T12:08:17Z carries `model_version` or `generated_at` at all.
- `HistoryTapeRow.win_probability_p1`: documented that the tape carries no model-regime stamp — no `model_version` or `generated_at` column here or in the bulk `tape` packages — so a recorded tape corpus is segregated by the row's own `timestamp` against those two instants.

Documentation only. No field, endpoint or wire value changed.

## [1.13.18] - 2026-09-19
### Fixed
- `LivePoint.number` (`GET /matches/{matchId}/points`, the `point` frame, the webhook `point` event): the field is documented as **null when we joined the game already in progress**, and the API now writes null there instead of `0`. `0` asserts a game's opening state, and on a game we picked up mid-way that is false — how many points it already holds is not derivable from the score, because the deuce zone maps many ordinals onto one score, and it is never guessed. Measured on 2026-09-19, 1,341 rows over three days carried `number: 0` at a non-love score. A second defect in the same computation is fixed with it: a late-arriving row for a *different* game committed between two points of the game in progress reset the ordinal, so on match 191801 `seq` 65 and 67 were both `(set 2, game 1, number 0)` — at 15-15 and 15-40 — with `seq` 66, a point of set 1 game 9, between them. The ordinal now continues within its own game regardless of what arrived in between. The schema already permitted null; only the description and the written values change.
### Changed
- Documented, in all three places the replay guidance appears, that `(set, game, number)` **orders** points and does not **identify** them: the tuple may repeat, and `number` may be null. A repeat on the live basis is a re-statement of a game by a second source, not a correction — there is no revision id, superseded-`seq`, version or correction flag, because rows are append-only and never rewritten. `after_seq` therefore never needs a full refetch, and the page-level `quality` field already reads `revised` when a page contains such a re-statement. `seq` remains the only unique, stable per-row key.

## [1.13.17] - 2026-09-18
### Added
- Native WebSocket **close codes**, documented for the first time. Every refusal sends its `error` frame and then closes with a code that says what to do next — `1013` Try Again Later for transient refusals (`connection_limit:per_key`, `connection_limit:server`, `service_unavailable`), `1008` Policy Violation for anything a retry cannot fix (`unauthorized`, `upgrade_required`, `email_unverified`, `client_blocked`, `bad_json`, `no_topics`, and any mid-stream loss of access), `1012` on a restart, `1000` on a normal close. The close reason repeats the frame's `error` string, so `(code, reason)` is a complete diagnosis even if the frame was missed. Behaviour change the same day: refusals raised during the *handshake* previously closed `1000` with an empty reason, indistinguishable from an orderly shutdown, so a client awaiting its `subscribed` ack saw only a normal close. The error frame was, and still is, delivered before the close; only the close code and reason changed.
### Changed
- `GET /matches/{matchId}/points`, the `point` frame and the `points` signal: **`seq` is arrival order, not match order, on the live basis.** It is assigned in commit order, and a live match is fed by more than one upstream at different speeds, so a point from a set that has just ended can be committed after points from the set that follows it and carry the higher `seq`. Each row is self-consistent; reading the tape in `seq` order can show the set or game counter step backwards. Measured over a recent seven-day window this affected a minority of live matches, and never the `reconstruction` basis. `seq` remains the right key for paging, dedup and resume, and is the wrong key for chronology — sort by `(set, game, number)` to replay in playing order. The spec previously said "ordered per match by `seq`", which reads as chronological. Documentation only; nothing on the wire changed.

## [1.13.16] - 2026-09-18
### Changed
- `GET /usage` → `today.remaining_day`: documented as the day allowance less **SERVED** calls (`calls - errors`), and the API now computes it that way. Refused requests have never spent the daily allowance — the `429` guidance in this spec already said so — but the endpoint subtracted gross calls, so it under-reported what a key could still send by exactly its error count. Measured on 2026-09-18, one ULTRA key was shown 14,360 fewer requests remaining than the API would have served it. `today.calls` and `today.errors` are unchanged: raw counters of everything the key sent.

## [1.13.15] - 2026-09-18
### Fixed
- `event_status` (match object): the enum omitted **`Finished`** and **`Unresolved`**. `Finished` is the value the field carries on a normally-completed match and is by far its most common — 144,266 of the 150,678 rows carrying one, measured on 2026-09-18 — so a client generated from this spec with strict enum validation rejected the majority of completed matches. Both values are listed now. The API has always published them; only the spec was wrong, so nothing on the wire changed.
### Changed
- `event_status` description: "NULL means the match completed normally" was wrong in the direction that matters — null means the feed never stated anything for the match, which covers matches that ran their course and matches nothing was ever said about alike. Branch on `outcome`, not on the absence of a badge.
- `event_status` description: `event_status: Finished` while `status` is still `live` is documented as the pending-final state (one source has called the match over, the final is not confirmed). The score stands still through it — `stale` true, `age_seconds` climbing. Measured over the seven days to 2026-09-18, across 649 matches, that gap closed in 111 s at the median and 911 s at the ninetieth percentile; 85 ran past ten minutes.

## [1.13.14] - 2026-09-17
### Changed
- Plan end: when a paid plan's period ends (or a renewal goes unpaid) the same key now drops to the FREE tier automatically instead of being switched off — nothing is re-issued, free endpoints keep answering at the free limits, paid endpoints answer `403 upgrade_required` from that moment, and subscribing again lifts the same key. Behaviour change on the billing side effective 2026-09-17 19:59 UTC; keys of plans that ended in the previous 30 days were moved to FREE the same evening. No field or endpoint changed.

## [1.13.13] - 2026-09-17
### Changed
- `GET /history/matches/{matchId}` `tiebreaks` / `meta.tiebreaks_source`: the timing was stated wrongly. The `summary` and `reconstruction` kinds were described as "recorded at completion"; they are written by a finals pass that runs once a day, so a match that finished earlier the same day commonly reads null for its 7-6 sets and carries them from the next pass onward. Only the `tape` kind is available the instant a match ends. Measured 2026-09-17: 72-100% of 7-6 sets populated on matches completed over the five previous days, 8% on matches completed the same day. Documentation only — no behaviour or field changed.

## [1.13.12] - 2026-09-16
### Changed
- `GET /history/matches/{matchId}` `tiebreaks`: per-set breaker finals are now filled from the point-by-point reconstruction and from the sources' set summaries when the live tape stopped one point short (measured before this change: null on about 99% of 7-6 sets — 297 measured, 3 populated). New `meta.tiebreaks_source` says, per set, whether the final came from `tape`, `summary` or `reconstruction`. The response shape is unchanged.

## [1.13.11] - 2026-09-16
### Added
- `GET /players/{playerId}/stoppages` (PRO) and its alias `GET /players/{playerId}/injuries`: one player's in-match stoppages (medical timeouts, trainer calls; toilet breaks, pauses and other stoppages on request) plus the matches the player retired from or gave a walkover, newest first, over a window that defaults to the last 180 days. `meta.latest_medical_timeout` / `previous_medical_timeout` answer "the latest and the one before"; `meta.record_starts` states where each record begins (stoppage events from 2026-09-12; outcomes from 2026-08-18). In-match stoppages and match outcomes only; there is no off-court injury record.

## [1.13.10] - 2026-09-15
### Changed
- `Score.sequence`: a backwards move on `GET /matches/{matchId}/score` has two documented causes, not one — a withdrawn state, or the read deferring to a strictly higher-trust source's fresh state (about 1% of live reads). On the push feed and the native WebSocket the sequence only ever rises.

## [1.13.9] - 2026-09-15
### Added
- `Score.accepted_at` (string|null, live score reads and push frames): the instant we accepted this state, stamped once and never refreshed — the clock to difference a latency study against.
### Changed
- `Score.timestamp` documented for what it is: our clock, stamped at acceptance and then refreshed (at most every 8 s) while the owning source keeps re-asserting an unchanged state, so on a live read it is usually the last-assertion instant. It was described as "when this state was true"; it never was. Never an upstream observation time.
- The `Score` schema on this site now carries the full field set and descriptions: `sequence`, `age_seconds`, `stale`, `observed_age_seconds`, `sources_count` and `detail` were missing from the published table, and `sets`/`server`/`is_tiebreak`/`win_probability_p1`/`danger`/`timestamp` had no description.

## [1.13.8] - 2026-09-15
### Changed
- Wording correction to 1.13.7: the pre-match hold rates enter the engine **snapped to a 0.01 grid**, not "rounded to three decimals". The mechanism and every field are unchanged; only the stated granularity was wrong.

## [1.13.7] - 2026-09-15
### Changed
- `win_probability_meta.market_anchored` is documented for what it always was: the market-prior anchor **applies to this match** (a two-sided pre-match price and a pre-play first score). It was described as "whether the anchor moved `win_probability_p1`", which is a per-row claim the flag never made — a small anchor shift can solve to a probability identical to `win_probability_p1_model`. Recorded values keep their meaning.
### Added
- `win_probability_meta.anchor_effective` (boolean|null): this row's `win_probability_p1` differs from `win_probability_p1_model`. The per-row test `win_probability_p1 != win_probability_p1_model` works on frames recorded before this field existed.

## [1.13.6] - 2026-09-15

### Added
- `GET /history/matches/{id}/prices` (PRO): the per-point price history — one row per played point with the
  score state the BASIC tape publishes and, per neutral side, the match-winner quote in force when the point was
  captured (`bid`, `ask`, `mid`, `spread`), with `lag_seconds` and an honest `resolution` label (`tick`, `minute`,
  `coarse`). Works on a live match too; 404 `no_market` when no market is mapped.
- `GET /history/matches?has_market=true|false` and a `has_market` flag on every history row, so a match with a
  price tape can be enumerated before it is pulled.

### Changed
- Price retention: from 2026-09-15 the in-play ticks of a match with a mapped market are kept at full resolution
  and are not deleted; pre-match and idle ticks keep the existing tiers. Earlier ticks were already thinned.
- `GET /matches/{id}/prices` answers 404 `no_market` for a known match without a market (it said `not_found`).

## [1.13.5] - 2026-09-14

### Changed
- `pbp_coverage: "point"` now means a per-point stream has **delivered** for the match — at least one
  played point past the `seq` 1 opener. Until then it reads `"game"`, including for a listed match whose
  stream holds only its opener because play has not started. Previously any point row, including the
  opener written before the first ball, was enough for `"point"`, so a client told to gate on the field could
  subscribe to a match that never advanced. The admission gate we recommend is `sequence > 1` together with
  `stale: false`. On the server, a match flagged live whose entire tape is still opener rows is demoted back to
  upcoming after twenty minutes, so such matches no longer linger in the live list.

## [1.13.4] - 2026-09-14

### Added
- ITF World Tennis Tour **qualifying rounds** (singles) are now listed and live-scored from the ITF's own
  live scoring: matches appear in `GET /matches` with `round`, `tournament` and `scheduled_time`, receive
  live scores while in play and complete on the feed's result. Sundays and Mondays, the qualifying days,
  were previously almost empty because the schedule feed carries main draws only. `GET /fixtures` still
  mirrors the schedule feed and does not list qualifying.

## [1.13.3] - 2026-09-13

### Changed
- WTA / WTA 125 stoppages now arrive in two layers. The console's match state is read within
  about 20 seconds and yields `trainer_called`, `toilet_break_*` and `stoppage_*` rows (player
  null). The console's event feed, which the tour publishes with a variable delay — measured on
  2026-09-13 from about one minute to an hour behind play — adds `medical_timeout_start/end` with the player and the exact instants. The
  1.13.1 note implied the event feed was live; it is not.

## [1.13.2] - 2026-09-13

### Added
- ATP main-tour stoppages: a public live-score service's match stage is now watched for its
  medical-timeout and interruption stages. Those stages exist in the vocabulary but have not yet
  been observed on a tennis match, so ATP rows are documented as mapped, not yet proven; they
  carry `player: null` and an `at` equal to the instant the stage was observed.

### Changed
- ITF coverage note: the first medical timeout was observed and published on 2026-09-13.

## [1.13.1] - 2026-09-13

### Added
- Scorer-stated stoppages for **WTA and WTA 125** singles: `medical_timeout_*`, `trainer_called*`,
  `toilet_break_*` and `stoppage_*` rows now come from the chair umpire's console for those tours
  (measured over 138 finished matches: 27 physio calls, 65 treatment records, 22 suspensions).
  Same fields, same endpoints, same WebSocket signal. `stoppage_start.reason` gains `heat`,
  `darkness` and `injury`; every `stoppage_end` carries `reason: "resumed"`.

- Scorer-stated stoppages for **ITF World Tennis Tour** singles from the court's live-scoring
  state: `toilet_break_*`, `medical_timeout_*`, `trainer_called*` and `stoppage_*` rows on entering
  and leaving the state, with `duration_seconds`; `player` is null on these rows because the feed
  names the state, not the player.

### Changed
- Coverage note: WTA, WTA 125, Challenger, UTR and ITF singles are covered; ATP main tour is still
  being sourced and is stated as not covered.

## [1.13.0] - 2026-09-13

### Added
- `GET /events` (PRO): the **slate-wide events feed** — the rows of `GET /matches/{id}/events`
  for every match in one call, oldest first, cursor by `after_id` (`meta.next_cursor`, null =
  caught up), `since` as the first-call UTC lower bound, `type` as a comma-separated list of
  event types or the family name `stoppages`. Rows carry `id` and `match_id`. One request per
  tick covers the whole live slate: medical timeouts across every live match on PRO by polling.
- `SlateEvent` schema; `Event.type` documents the full vocabulary.

### Changed
- Stoppage coverage, corrected: scorer-stated `medical_timeout_*`, `trainer_called*` and
  `toilet_break_*` rows exist for **Challenger and UTR singles**. The 1.11.0/1.12.0 text said
  ATP, WTA and WTA 125 as well; measured over 11 days those tours' scorer feed carries none
  (0 of 70 finished matches each, against 22 of 70 for Challenger). Main-tour and ITF medical
  timeouts are being sourced; the note changes the day they are live.

## [1.12.0] - 2026-09-12

### Added
- **`serve` and `outcome` on live point rows** (`GET /matches/{matchId}/points`, the
  `point` frames): the serve the point was played on (1 | 2) and how it ended
  (`ace` | `double_fault` | `winner` | `forced_error` | `unforced_error`), as an
  outside source states them, joined onto our rows by exact state; `null` when not
  stated. Coverage per match in the new `enrichment` object; per tour in the reference.
- **`point_update` frame** on the point opt-in — a point's `serve`/`outcome` landing
  after its `point` frame; apply by `seq`.
  Asked by an ULTRA customer trading on serve outcome.
- **`published_at`** on every data frame of the native WebSocket and the push feed:
  the UTC instant (ms) the frame left our process — the third clock next to the
  state's `timestamp` and a point's `ts`, so processing and transport latency can be
  separated. Asked by a prospect running a latency benchmark.

## [1.11.0] - 2026-09-12

### Added
- **Medical timeouts, trainer calls and toilet breaks as events** on
  `GET /matches/{matchId}/events`: `medical_timeout_start/end`, `trainer_called/_end`,
  `toilet_break_start/end`, each with `player` (the player concerned), `at` (UTC),
  the `score` at that instant, `reason` and `duration_seconds` on the end row — as
  the match scorer states them (ATP, WTA, Challenger, WTA 125, UTR singles).
  `stoppage_start/end` now carry a stated `reason` (`weather` | `other`) when one
  exists. Asked by a prospect building on medical timeouts.
- **`pause_start` / `pause_end`** (`basis: inferred`): interruptions of play measured
  from our own point clocks, on every live match, never labelled medical.
- **`signals:["stoppages"]`** on the native WebSocket and the stoppage family on the
  `signal:*` push channels — every row above pushed the moment it is recorded.

## [1.10.1] - 2026-09-12

### Clarified
- A ranking tie is two rows with the same `rank` (doubles partners always tie).

## [1.10.0] - 2026-09-12

### Added
- **`win_probability_p1_model`** and **`win_probability_meta`** on ULTRA live score
  objects: the same model read computed without the market-prior anchor (a
  probability no market price touched), plus `model_version`, `generated_at` and
  `market_anchored` for the pair. `win_probability_p1` is unchanged. Asked by an
  ULTRA customer who needed to know whether the live probability is independent of
  market prices — on anchored matches it is not, and now the row says so.
- **`basis`** on status-ledger rows (`observed` | `backfill`); the ledger now reaches
  back to the per-match stamps held before it existed (completions from 2026-08-21,
  promotions to live from 2026-09-05), one reconstructed row per stamp, labelled.

- **`system=atp_doubles` / `system=wta_doubles`** on `/rankings`: the official
  weekly doubles tables (individual players), in both modes at the same gates as
  `atp`/`wta`, never included implicitly. Loaded from 2023 forward.

### Clarified
- Status-ledger rows are ordered by their instant (`at`), not insertion order.

## [1.9.9] - 2026-09-12

### Clarified
- The status ledger records from **2026-09-11T22:45:48Z** (its first row), not the
  calendar date of the deploy. Reported by an ULTRA customer reading match 188711.

## [1.9.8] - 2026-09-12

### Added
- **`GET /matches/{matchId}/status-history`** — the per-match status ledger:
  every `status` / `event_status` transition with the UTC instant we published
  it, the value before and after, the derived `outcome` and the score at that
  instant. Append-only, oldest first; rows exist from 2026-09-12. History
  capability (BASIC and the Historical Data plans). Asked for by a researcher
  reconciling corrections against the moment they were published.
- **`stoppage_start` / `stoppage_end` events** on `GET /matches/{matchId}/events`:
  an in-play suspension with the score at the moment, `reason` (`unknown` until a
  source states one — never inferred) and `duration_seconds` on the end row. Asked
  for by a product builder wanting medical timeouts as an event.

## [1.9.7] - 2026-09-10

### Added
- **`Match.outcome`** is now documented on the Match schema (it has been on
  every match since 2026-08-18): `completed | retired | walkover | default |
  abandoned | unresolved | null`, derived from `status` + `event_status`.
- **`outcome: unresolved`** — a match every source lost before a result is
  closed unfinished and says so: `score` is the last state observed, `winner`
  is null, no result is asserted; it flips to `completed` with the proven
  final when an authority confirms the result. Until 2026-09-10 such closes
  were published as `completed` with a mid-match score, which an ULTRA
  customer read as a wrong result.

## [1.9.6] - 2026-09-10

### Added
- **`stats.ratings_as_of`** on `GET /players/{id}` — the date (UTC) the `ratings`
  block was last refreshed. The current Elo is now refreshed every week for every
  rated player from the published rating tables (Tuesdays); before this the rating
  carried no date and a May capture read as this week's. Reported by a PRO customer
  building pre-match research.
- **`GET /history/packages/{period}?format=corrections`** — a CSV keyed by
  `match_id` (`match_id, field, before, after, tournament_key, source,
  corrected_at`) on every package whose stored data was repaired after publication,
  listed in the manifest as `format: corrections`; 404 when a package has none.
  First use: `surface` corrections on the 2023-02 → 2024-12 tape packages (19,439
  Challenger matches whose court surface a tournament-name rule had set to grass;
  repaired and rebuilt 2026-09-10). Reported by a History Pro customer.

### Fixed
- Merged player ids: a merge now repoints the weekly ranking tables too, so
  `/rankings` rows carry the same `player_id` the match records carry, and the
  retired id answers 410 with `merged_into` (see Merged and retired player ids).

## [1.9.5] - 2026-09-09

### Added
- **`GET /matches/{matchId}/prices?cursor=`** — keyset paging past 500 ticks:
  while `meta.has_more` is true, pass `meta.next_cursor` back as `?cursor=` for the
  next (older) page; pages never overlap or skip a tick; anything else is
  `400 bad_cursor`. Mirrors tennis 3123b27f (live 2026-09-09 06:01Z).
- **`Match.live_at`** — the instant our feed last reported the match in play
  (UTC), the closest thing to an actual start time. Null for matches that went
  live before 2026-09-05 or were never observed live. Same commit.
- **`410 Gone` with a `MatchMerged` body** on the ten per-match routes when a
  match id was merged into another record: `error: merged`, `merged_into`
  (the end of the chain, or null), `merged_at`, `detail`. Live since 2026-09-05
  (tennis d131a12f).
- **Tape point `is_unreturned` / `unreturned_kind`** (rally tapes, tennis
  6e7b82f6, 2026-09-05).

### Clarified
- Price ticks are kept for **30 days** and then deleted: an older match answers
  an empty `data` / `prices` array while its market stays mapped — retention,
  not a fault. Stated on both prices endpoints.

## [1.9.4] - 2026-09-09

### Fixed
- **`Price.side`** (per-match and per-market prices endpoints, and the match embed) now
  follows `players.p1` / `players.p2` through our name-verified match-market mapping.
  Until 2026-09-09 it followed the venue's display order, which lists roughly half of
  all pairings the other way round, so on those markets `side: 1` was in fact
  `players.p2`. The mapping is stored, so re-reading any tick - historical included -
  returns the correct side. Reported by a PRO customer cross-checking pre-match prices
  against rankings; mirrors tennis cbd3f647 (live 2026-09-09 04:59Z).

### Clarified
- `Price.mid` is the venue's observed midpoint, never a model estimate; `synthetic`
  describes only `bid`/`ask` (`mid` +/- 0.005 when true); pre-match ticks are
  `synthetic: true` by design because the live book attaches at match start;
  `timestamp` is our observation clock (UTC), not a venue publication time.

## [1.9.3] — 2026-09-04

### Clarified
- **`Match.tournament_id` null cases** restated with the real causes and a
  measured rate: not in the catalogue (UTR), or a secondary-source match whose
  name matched no single catalogue edition. The API now resolves the latter at
  ingest by name + event type + date against the vendor's own fixtures, and the
  2026 backlog was backfilled the same day (2,547 rows); ITF null rate went
  from about 25% to about 2.5%. No wire change.

## [1.9.2] — 2026-09-04

### Added (spec catch-up — every one of these has been live on the API; the document lagged)
- **`GET /matches?status=cancelled`** is now in the `status` enum, with what it
  covers (feed-cancelled, walkover with no stated winner, postponed and never
  played), its tier (BASIC or any History plan, like `completed`), and the one
  restriction: it pages with `limit`/`offset` and refuses `updated_since`.
- **`tournament_id=`** filter on `/matches` (every status) and `/history/matches`
  — the stable id each match row carries and `/tournaments` publishes. The
  description states there is no separate edition/occurrence id: one edition
  is `tournament_id` plus a `from`/`to` window, and matches with a null
  `tournament_id` (tournament not yet catalogued) fall outside the filter.
- **Change feed on `/matches`**: `updated_since=` / `cursor=` parameters and the
  `meta.next_cursor` / `meta.watermark` fields, with the at-least-once and
  no-`from`/`to` rules.

### Clarified
- `meta.has_more` says how to enumerate a filtered set completely (page
  `offset` by `limit` until false) and that `total` is null on the terminal
  listings, so `has_more` is the only end-of-data signal there.
  Asked by a Basic customer on Discord; no wire change.

## [1.9.1] — 2026-09-02

### Clarified
- **`Player.ranking` / `Player.ranking_points`** now say what they are: the
  official singles ranking POSITION (the ordinal), ATP table for men and WTA
  table for women chosen by the player, refreshed ahead of each match the
  player has with us, `null` when no ranking is held, and always the CURRENT
  record even on historical matches (`/rankings?as_of=` is the as-of surface).
  Asked by a Basic customer; no wire change.

## [1.9.0] — 2026-09-02

### Added
- **`has_analysis` and `has_market` on `Match`** — two booleans on every row of
  `GET /matches` and on the detail, every tier. They carry the same fact the
  per-match endpoints answer 404 about, so a slate is filtered in one call
  instead of one 404 per match. Shipped to production 2026-09-02.
- **Distinguishable absence on `GET /matches/{matchId}/analysis` and
  `GET /markets/{matchId}/prices`.** The status stays `404` (unchanged, and
  shipped clients branch on it), but the body now says which absence it is:
  `{"error":"not_found"}` for an id that does not exist, and
  `{"error":"no_analysis"|"no_market","match_id":…,"coverage":"none","detail":…}`
  for a real match we hold nothing for — the same `coverage: "none"` vocabulary
  `/matches/{matchId}/statistics` already uses in its `200`. New `error` codes
  `no_analysis`, `no_market` documented on the `Error` schema.

## [1.8.0] — 2026-09-01

### Added
- **`GET /history/archive/matches/{archiveId}/tape`** (`getArchiveTape`) — the
  RECONSTRUCTED 2013–2022 point-by-point tape for one archive result: the score
  sequence behind the published result, rebuilt from the public record after
  the fact. Shipped to production 2026-09-01; the spec was the last place it
  was missing. Tier: core ULTRA, **or any active History plan including
  Starter** (which opens it on a FREE core key). The archive RESULT stays on
  BASIC, so core BASIC and core PRO read the result and are refused the tape —
  `403 upgrade_required` carrying `capability: archive_tape`.
- **`ArchiveTape` schema.** Same envelope as `HistoryTape` so one parser reads
  both halves of the tape product, with the differences that are true: `match`
  is the winner/loser-shaped archive row (rows are WINNER-FIRST, not p1/p2),
  `profiles` is always `[]`, and `meta` carries `archive_match_id` rather than
  `match_id` — an archive id is not a match id, and passing one to the other's
  routes resolves a different, real record without erroring. Rows are
  `HistoryTapeRow`, reused unchanged.
- **`kind=archive_tape` on `/history/packages` and `/history/packages/{period}`,
  and on `HistoryPackage.kind`.** Ten per-year bulk files, `period` 2013 through
  2022, JSONL + CSV, all `ready`. The JSONL record is byte-for-byte what the
  per-match endpoint returns; the CSV is the flat per-row view keyed on
  `archive_match_id` and deliberately carries no `timestamp`,
  `win_probability_p1` or `danger` column. A SEPARATE gate from the per-match
  tape: ULTRA, a History Pro/Business subscription, or an active one-off package
  window — a Starter grant reads tapes one at a time and does not download years
  of them. **Core PRO carries neither gate.**

### Changed
- **`info.description` states the provenance and the coverage, thin spots
  included.** Nobody watched these matches: `timestamp`, `win_probability_p1`
  and `danger` are null on EVERY row and cannot be filled in later — the
  production table has no timestamp column at all, so this is a structural fact
  and not a convention. That is the opposite of the 2023→now tape, which is our
  own recording, where the rows we actually watched carry a real clock and most
  of them a model probability. The corpus is 97,901 matches / 14,340,663 rows,
  seasons **2013–2022 only**: 977,903 archive results from 1968–2012 have no
  tape and never will. Coverage of the era is 19.3% overall and 44.9% of
  tour-level play — main-draw tour buckets 91.6–98.7%, ATP Challenger main
  55.3% and Challenger qualifying 33.6%, slam QUALIFYING 16.0% (ATP) / 18.1%
  (WTA), ITF and futures effectively zero (25 of 116,575 ATP futures). Stated
  together, because a strong number published without its thin counterpart sells
  a corpus nobody has.
- **`ArchiveTape.meta.coverage` names the measured split rather than glossing
  the label.** `reconstructed_partial` (3,594 matches) has TWO causes and does
  not say which: 3,038 are point-granular tapes of matches that genuinely
  stopped early (3,027 retirements, 11 defaults) — the larger cause — and the
  other 556 carry the label only because their tape is per-GAME. Read
  `granularity` and the match's own score, not the label, when the question is
  whether the whole match is there. `granularity` is `point` on 99.4% of the
  corpus; the 556 `game` tapes are 555 in 2013 and one in 2014.
- **`Coverage` says where its vocabulary stops.** It describes the 2023+ tape;
  the archive tape reuses two of its five values and derives
  `reconstructed_partial` differently.
- **`ArchiveMatch` points at the tape**, and `GET /history/archive/matches/{archiveId}`
  says the RESULT stays on BASIC either way.
- The plain-HTML reference gains an FAQ entry — "Is there point-by-point data
  before 2023?" — and the history FAQ, `llms.txt` digest and README plan summary
  carry the same numbers, so an answer engine reading any one of them gets the
  corpus, the null clock and the coverage floor together.
- `info.version` is now `1.8.0`.

## [1.7.2] — 2026-08-23

### Changed
- **`status` on Match now documents the lifecycle rule.** `completed` is
  asserted only for a match we observed being played or whose match-winner
  market settled decisively; a closed market alone never finishes a match.
  `cancelled` with `event_status: null` means positive evidence the match
  was not played as scheduled (the market settled void) and no vendor word
  for why — `outcome` / fixture `reason` stay null rather than guessed, and
  the row upgrades to a completed walkover if a `Walk Over` with a stated
  winner lands later. Before 2026-08-23 a void market closure completed the
  match and stamped `Finished`; those rows were corrected. No field added or
  changed type — prose only.
- `info.version` is now `1.7.2`.

## [1.7.1] — 2026-08-19

### Added
- **`event_status_updated_at` on Match.** Nullable ISO-8601 UTC (`Z`)
  timestamp, right after `event_status`: when `event_status` last CHANGED —
  the instant WE recorded the walkover / retirement / cancellation /
  postponement / suspension (or its clearing), not when the tournament desk
  or the feed did. It is the field to measure our admin-status latency with.
  Bumps only on a change of value (a re-read of the same status never moves
  it; a clear back to null does). Null while `event_status` has never changed
  since the field was introduced (2026-08-19) — never backfilled, never
  guessed. Inherited by every schema built on Match (`MatchDetail`,
  `HistoryMatch`). Additive only — no existing field moved or changed type.

### Changed
- `info.version` is now `1.7.1`.

## [1.7.0] — 2026-08-18

### Added
- **`basis` on `GET /matches/{matchId}/points` responses.** `live` |
  `reconstruction` — which base served the page. Live capture is inherently
  partial: the stream serves what arrived while the match ran, and the
  match-closing point never streams live. For a COMPLETED match where a
  measured-complete recorded point sequence exists, the endpoint now serves
  that complete sequence instead, projected into the same point-frame shape
  — love-love opener through the match-closing point, `seq` contiguous
  `1..N`, `quality` `clean` — and says so with `basis: "reconstruction"`.
  Every other case (every live match, and any completed match without a
  measured-complete recorded sequence) stays `basis: "live"` — the persisted
  stream rows, byte-for-byte what was served before. Completeness beats the
  partial live capture WHOLESALE — the two sequences are never interleaved
  (they share no key, so any merge would fabricate an order), the same rule
  `?points=complete` follows on the history read. On projected frames `ts`
  is null on every row: the recorded sequence carries no per-point clock and
  none is fabricated (`LivePoint.ts` now documents this). `after_seq`
  pagination and `seq` dedup work identically on either basis, but the two
  bases are different sequences: after a match completes and flips to
  `reconstruction`, re-read from `after_seq=0` rather than resuming a live
  cursor into it. Additive only — no existing field moved or changed type.

### Changed
- `info.version` is now `1.7.0`.

## [1.6.0] — 2026-08-18

### Added
- **The three-valued `draw` field on Match.** `singles` | `doubles` | null —
  same vocabulary as the new `?draw=` filter, decided by one shared
  definition, so filter and field cannot disagree. Evidence order: a
  doubles-team participant proves doubles over any event type; otherwise the
  feed's event type decides. Null means neither says anything — no stated
  event type, or a team tie (Davis Cup / BJK Cup / United Cup class), where
  one event type covers both singles and doubles rubbers and we will not
  guess which this is. Null is NOT singles. `is_doubles` stays for
  compatibility and is now documented as LOSSY, with its evidence order:
  false also covers "unknown", which is not a claim of singles — prefer
  `draw`, whose null says so honestly.
- **`?draw=singles|doubles` on four listings** — `GET /matches`,
  `/history/matches`, `/tournaments` and `/fixtures`: the axis the `tour`
  filter deliberately collapses; the two compose (`?tour=itf&draw=doubles`
  is the ITF doubles slice). A row whose draw is null matches NEITHER value
  — null is an answer, not a wildcard. An unknown value is a 400 `bad_draw`
  with the allowed values. Two honesty notes carried into the spec: on
  `/tournaments` the answer comes from the event type alone (a tournament
  row has no participants to supply the doubles-team evidence matches
  have), and `?draw=doubles` alone also returns mixed and exhibition
  doubles that no `?tour=` value reaches.
- **`GET /history/coverage`** (BASIC, or any Historical Data API plan) —
  the measured completeness rollup per tour × draw bucket: the numbers to
  read BEFORE choosing what to backtest, in one call instead of paging the
  archive. A prebuilt snapshot rebuilt nightly right after the completeness
  ledger reconverges — never computed at read time — so `as_of`
  (= `built_at`) dates every number and `ledger_max_computed_at` is the
  newest underlying per-match measurement; `503 coverage_unavailable`
  before the first nightly build. Buckets are atp/wta/challenger/itf/juniors
  × singles/doubles plus `other` (team ties, mixed, exhibitions and matches
  with no stated event type — counted, never dropped, so the totals cannot
  lie); a bucket with zero completed matches is OMITTED, never emitted as
  zeros. Each bucket carries the five verifiable numbers (`completed`,
  `any_tape`, `point_complete`, `complete_on_default_read`, `share`), and
  `method` states the full measurement rule so every number carries its own
  definition. As of 2026-08-18: 174,393 completed matches; 91,318
  point-complete on the best basis (52.4%) against 81,196 on the default
  read alone (46.6%); ITF singles 51.1% against ITF doubles 3.5% — do not
  extrapolate a completeness rate across a tour group.
- **`tape.starts_at_love` and `tape.computed_at` on `/history/matches`
  items** (both nullable, present where enabled). `starts_at_love` follows
  the SAME best-basis rule as `points_complete` — true when either measured
  basis opens at the 0-0 state, so if any on-disk sequence opens at love
  you can obtain one that does. `computed_at` is when the ledger last
  measured the match: every field in the tape's measured block is a
  nightly-reconverged cache, and this is the as-of to quote with any of
  them. Null on either means the match has not been measured — never a
  guess.
- **The complete-basis addendum package files.** An affected month's
  manifest may also list
  `tennis_history_points_complete_<period>.jsonl.gz` / `.csv.gz` (marked
  `compression: gzip`; `bytes`/`sha256` cover the compressed bytes —
  exactly the download): for exactly the matches whose complete point
  sequence exists only as the on-disk reconstruction, the same tape
  `?points=complete` serves (reconstruction contract: null timestamps and
  null model fields). The base files keep carrying every match's DEFAULT
  read — already the complete tape for most point-complete matches — and
  are never rewritten by the addendum; their `bytes` and `sha256` values do
  not move.

### Changed
- `info.version` is now `1.6.0`.

## [1.5.0] — 2026-08-17

### Added
- **The as-of Elo tape.** `GET /rankings?system=elo` (ULTRA, both modes) —
  our own computed Elo as point-in-time records: per-player as-of (also via
  `archive_player` for the ~62,000 rated people outside the roster, `tour`
  required there) and a leaderboard (`tour` required — the ATP and WTA walks
  are disjoint; exactly one `surface`, default `overall`; `min_matches`
  default 20 and `activity_weeks` default 52 / max 104, both echoed in
  `meta.coverage.qualified`). Four independent ladders
  (overall/hard/clay/grass), ATP from 1877, WTA from 1968, main tours plus
  challengers plus the futures tier. `rating` always; `rank`
  leaderboard-only; `points` always null; `matches` is the ladder-scoped
  count. `meta.coverage` gains `newest_available`, `players_rated` /
  `players_linked`, `qualified` and the `model` block
  (`publication_lag_days: 14` — a week's results become effective 14 days
  after the week begins, so the failure direction is staleness, never
  look-ahead). The corpus head is frozen at 2026-05-25 and does not
  advance; `elo` is never included implicitly. The free current Elo on
  `GET /players/{id}` is a DIFFERENT scale (~150 Elo of per-player standard
  deviation apart) — never present a rating from one scale against a rating
  from the other. `kind=elo` yearly bulk packages join `/history/packages`.
- **`covers_from_start` on `GET /matches/{matchId}/points`** (bool|null):
  whether the persisted stream opens at the match's 0-0 opener (seq 1 is
  the love-love state) — strictly affirmative; null only when the match has
  no rows at all.
- **The point channel family enters the `/ws-token` vocabulary.**
  `point:match:{match_id}` / `point:slate` are documented as
  `point_match` / `point_slate` in the channel vocabulary, listed only when
  the point feed is enabled server-side and the key's plan carries the
  point surface. A channel named in that response is a promise; a missing
  one will not deliver.

### Changed
- **Measured statistics stop rounding the truth.**
  `MatchStatisticsMeasured` now states: match totals only (no per-set
  measured statistics); absent = not measured while a present 0 is a real
  measured zero; the three coverage tiers with their hard zeros — the
  winners/unforced/forced-errors family historically on ~43% of ATP
  singles, ~24% of WTA singles and ~47% of tour doubles, and NONE of
  Challenger, ITF or juniors (24,552 payloads, 2026-07-31) — and that the
  upstream feed has not delivered that family since 2026-07-12 (0 of 4,513
  August payloads carry it, measured 2026-08-17).
- **`errors_total` is documented as the total of FORCED errors**, with the
  evidence (3,766 payload sides, June–July 2026: equals the per-stroke
  error sum in 96.2%; smaller than `unforced_errors_total` in 11.7% of
  sides — impossible for a superset; per-match points accounting closes
  only under the forced reading, median residual 0 over 367 matches).
  Total errors = `errors_total` + `unforced_errors_total`; the `*_errors`
  shot family is the forced-error breakdown, and `groundstroke_errors` =
  `forehand_errors` + `backhand_errors`, a rollup rather than an addition.
- **UTR honesty.** `system=utr` is documented as observed from UTR's public
  search: withheld ratings are ABSENT, never 0; per-player as-of only — no
  listing by design (a table of only the players we happen to track would
  be a fake leaderboard); history since 2026-07-29; and the sweep's
  deliberate rankless / no-Elo (ITF-skewed) bias with its measured
  coverage (2026-08-17, players active in the last 60 days): ITF 931 of
  5,606 (16.6%), Challenger 197 of 1,903 (10.4%), WTA 43 of 573 (7.5%),
  ATP 15 of 525 (2.9%).
- *(recorded retroactively)* On 2026-08-16 the `/ws-token` description was
  expanded in place to teach the push-feed protocol (Centrifugo v2
  connect/subscribe/heartbeat, token-per-reconnect, the SDK `PushStream`
  pointer) without a version bump; this entry is the changelog record of
  that change.
- `info.version` is now `1.5.0`.

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
