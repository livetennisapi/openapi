<a href="https://livetennisapi.com"><img src="https://docs.livetennisapi.com/icon-256.png" width="72" height="72" alt="Live Tennis API"></a>

# Tennis scoring fixtures in IPTC SportsML

Six synthetic tennis matches, each written two ways. One is the score states of the Live Tennis API `Score` object. The other is an IPTC SportsML 3.1 document. They cover scoring edge cases that a tennis data format has to handle.

[Mapping page](https://docs.livetennisapi.com/sportsml.html) · [Score schema](https://docs.livetennisapi.com/reference.html#schema-score) · [Notation formats compared](https://livetennisapi.com/data/notation) · [Live Tennis API](https://livetennisapi.com)

**Every match here is synthetic.** The players are "Player A (synthetic)" and "Player B (synthetic)". No player, match, score or date in this folder is real.

## The fixtures

| File | What it covers |
|---|---|
| `01-deciding-set-tiebreak` | The third set reaches 6-6 and a seven-point tie-break decides it, 9-7. |
| `02-match-tiebreak` | A ten-point match tie-break replaces the third set and ends 10-8. |
| `03-no-ad` | Two no-ad games reach 40-40. One deciding point is a break and the other wins the match. |
| `04-retirement` | Player B retires serving at 15-30 in the second set. |
| `05-walkover` | Player A withdraws before a ball is struck. There are no score states. |
| `06-default` | Player A is defaulted at 30-40 in the second set. |

Each name has a `.json` and a `.xml` file in `fixtures/`.

## The JSON file

- `states` is a list of `Score` objects, one after each point. Each one carries `sets`, `games`, `points`, `server`, `is_tiebreak`, `timestamp`, `accepted_at` and `sequence`. The other `Score` fields are left out because they hold model and freshness data.
- `match` carries `Match` fields: `format`, `status`, `outcome`, `winner`, `withdrew` and `players`.
- `rules` is not an API field. It tells the check script how the match is scored. It gives the number of sets, whether games are no-ad and how the last set is played.

A fixture starts late in the match, at the first state that matters. Its `sequence` values start at 201, 301 and so on for that reason.

Where the `Score` schema leaves a choice open, the fixtures make one:

- Each state is the score after one point. When a set ends and the match goes on, the next set's slot appears in `games` straight away at 0-0.
- During a tie-break, `points` holds the running count as strings. During a match tie-break, the deciding set's slot in `games` holds the same count, as the schema describes.
- After the last point, `points` is 0-0, `server` is null and `is_tiebreak` is false. The deciding set's slot keeps the match tie-break's points. The schema says that set is often published as 1-0 instead.
- `timestamp` equals `accepted_at`, since nothing re-sends a state.

## The SportsML file

Each document is a standalone `sports-content` document, valid against `sportsml.xsd` from SportsML 3.1. It has the two players, their sets and games, how the match ended, and one `action` per point. The [mapping page](https://docs.livetennisapi.com/sportsml.html) explains each choice. In short:

- `player-stats/@score` holds sets won. `stats-tennis-set` holds the games in each set, with `score-tiebreaker` for a tie-break set.
- A match tie-break is written as a set won 1-0, with its points in `score-tiebreaker`.
- Each `action` carries `sequence-number` and `created` from the state that point produced, the `set` and `game`, and three participants. Their roles are `ltapirole:server`, `ltapirole:receiver` and `ltapirole:point-winner`. These are our own codes, because IPTC publishes no tennis role codes. No IPTC catalog declares the `ltapirole` alias.
- `server-score` and `receiver-score` use IPTC's `sptengameresult` codes. A tie-break point has none, as the list has no code for a tie-break count.
- A retirement, a walkover and a default use the event status `forfeited`. The note holds our outcome value, and the first two add the reason `withdrawal`.
- When play stops inside a game, `event-metadata-tennis` gives the set, game, server and score at that moment.

## Check the fixtures

```
pip install lxml
python examples/sportsml/check_fixtures.py
```

The script checks that the schema files in `iptc-sportsml-3.1/` match their pinned SHA-256. It validates every SportsML document against `sportsml.xsd`. It then replays every point in the document from the first JSON state with the rules of tennis. Each result must equal the next JSON state. Last, it compares sets, games, tie-breaks, the winner and the way the match ended. It reads only local files and refuses a document with a DOCTYPE.

`test_check_fixtures.py` breaks copies of the fixtures one way at a time and checks that the script fails:

```
python -m unittest examples/sportsml/test_check_fixtures.py
```

## Licence

The fixtures in `fixtures/` are licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Credit "Live Tennis API" and link to https://livetennisapi.com.

The scripts are under the MIT licence of this repository. The files in `iptc-sportsml-3.1/` are IPTC's, under IPTC's own terms. See [SOURCE.md](iptc-sportsml-3.1/SOURCE.md).

This folder is our own work. IPTC has not reviewed it.
