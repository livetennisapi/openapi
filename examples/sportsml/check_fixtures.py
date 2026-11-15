#!/usr/bin/env python3
"""Check the synthetic SportsML tennis fixtures.

For every fixture in fixtures/ this script:

1. checks that the vendored IPTC schema files are byte for byte the ones published at
   https://www.iptc.org/std/SportsML/3.1/specification/ (SHA-256 pinned below),
2. validates the SportsML document against sportsml.xsd, which includes the tennis plugin
   sportsml-specific-tennis.xsd,
3. replays the points in the SportsML document from the first JSON score state, using the rules of
   tennis, and checks that every replayed state equals the next JSON state,
4. checks that the result in the SportsML document (sets, games, tie-breaks, winner, status) agrees
   with the JSON fixture.

It reads only local files. XML is parsed with entity expansion, DTD loading and network access
turned off, and a document with a DOCTYPE is refused.

Usage, from the repository root or from this folder:
    pip install lxml
    python examples/sportsml/check_fixtures.py

Exit status 0 when every fixture passes, 1 otherwise.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from lxml import etree
except ImportError:  # pragma: no cover - depends on the environment
    sys.exit("check_fixtures.py needs lxml: pip install lxml")

HERE = Path(__file__).resolve().parent
SCHEMA_DIR = HERE / "iptc-sportsml-3.1"
FIXTURES = HERE / "fixtures"
NS = "{http://iptc.org/std/nar/2006-10-01/}"

# SHA-256 of each file as published at https://www.iptc.org/std/SportsML/3.1/specification/,
# fetched 2026-11-15. The same bytes are in the official SportsML_3.1.zip package.
PINNED = {
    "NewsML-G2_2.22-spec-All-Power.xsd": "ea31ca7189762cb8a19402a5dd831be3652270e3576d8704577b4f1b9f308899",
    "sportsml-specific-american-football.xsd": "d3e35a67274e1e4336e7b0cb2404955aeba053e0e5d675d7f9d8e69350864e75",
    "sportsml-specific-baseball.xsd": "b15141c44159d6adf16c8d9a8d57351bb10d95d28f9e6e326ba7219c3be1406c",
    "sportsml-specific-basketball.xsd": "7af008dbf358f221806d1c04e1e762b5f674338fd5df6a0a735bb6da8c1ba907",
    "sportsml-specific-curling.xsd": "eee73c4932e8658bacd4a1a35d7d7aafaa7b3bd65ef99804cde3424f85803c5c",
    "sportsml-specific-golf.xsd": "9340b91e96a875f008f138fbddaf2b9c89f451f6c317ccb4bd7148801a6fdedc",
    "sportsml-specific-ice-hockey.xsd": "1a6350bf27b3f9af48e4cee2d88c9a71d25440b2892bb137b8104cc40bf7cd74",
    "sportsml-specific-motor-racing.xsd": "f30a4888e878f8459c26e1ae4852cdbfc086464f3a60890f8b199626951fbbe4",
    "sportsml-specific-rugby.xsd": "708c15b0f49cc228524bdc0e1c53b9126d0f21fec91052b411470a1f6e59f66c",
    "sportsml-specific-soccer.xsd": "f6d4412f710fdad6b9434421b9153b05453d4ae4a3c91f29bb7626c0b016361b",
    "sportsml-specific-tennis.xsd": "1c76a0f9a6ef9907025975e1e63b90b048c29df0b72e3baeda67d35c65ea0cf3",
    "sportsml-specific-volleyball.xsd": "4b62d65ee719a85dd5fdebdabf0304d67c608af68691dd610047d1d741f5a5ec",
    "sportsml.xsd": "7948f1ba12901afb228619c534a54eae2eb6f43c932e08a269df7fb431623a84",
    "xml.xsd": "87557312725ea4a6615729711f9e841b9edf3445ab03c9765e65127ba4ffb529",
}

# The six edge cases the folder promises. A missing one is a failure, not a smaller suite.
EXPECTED = ["01-deciding-set-tiebreak", "02-match-tiebreak", "03-no-ad", "04-retirement",
            "05-walkover", "06-default"]

# Match.outcome -> (event-status, event-status-reason, event-status-note) in the SportsML document.
OUTCOME_STATUS = {
    "completed": ("speventstatus:post-event", None, None),
    "retired": ("speventstatus:forfeited", "speventstatusreason:withdrawal", "retired"),
    "walkover": ("speventstatus:forfeited", "speventstatusreason:withdrawal", "walkover"),
    "default": ("speventstatus:forfeited", None, "default"),
}
FORMAT_SETS = {"BO3": 3, "BO5": 5}
# Our point strings -> the SportsML game score (sptengameresult on an action, gameResult.Tennis on
# event-metadata-tennis). Tie-break counts have no code in either list.
GAME_WORD = {"0": "love", "15": "15", "30": "30", "40": "40", "AD": "ad"}
STATE_KEYS = ("sets", "games", "points", "server", "is_tiebreak")


class FixtureError(Exception):
    pass


def safe_parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           dtd_validation=False, huge_tree=False)


def parse_xml(path: Path) -> etree._ElementTree:
    tree = etree.parse(str(path), safe_parser())
    if tree.docinfo.doctype:
        raise FixtureError(f"{path.name}: a DOCTYPE is not allowed")
    return tree


def load_schema() -> etree.XMLSchema:
    for name, digest in PINNED.items():
        path = SCHEMA_DIR / name
        if not path.is_file():
            raise FixtureError(f"missing schema file {name}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise FixtureError(f"{name} differs from the IPTC file (sha256 {actual})")
    return etree.XMLSchema(parse_xml(SCHEMA_DIR / "sportsml.xsd"))


# --------------------------------------------------------------------------- tennis rules


def other(player: int) -> int:
    return 2 if player == 1 else 1


def current_set(state: dict[str, Any]) -> int:
    """0-based index of the set in play: the last slot of each per-set games list."""
    return len(state["games"][0]) - 1


def is_match_tiebreak(rules: dict[str, Any], set_index: int) -> bool:
    return rules["final_set"] == "match_tiebreak" and set_index == rules["best_of"] - 1


def tiebreak_server(first: int, played: int) -> int:
    """Server of point number `played` (0-based) of a tie-break whose first server is `first`."""
    return first if ((played + 1) // 2) % 2 == 0 else other(first)


def tiebreak_first_server(state: dict[str, Any]) -> int:
    played = int(state["points"][0]) + int(state["points"][1])
    server = state["server"]
    return server if tiebreak_server(server, played) == server else other(server)


def set_won(rules: dict[str, Any], g1: int, g2: int) -> bool:
    at = rules["set_tiebreak_at"]
    return (max(g1, g2) >= at and abs(g1 - g2) >= 2) or max(g1, g2) == at + 1


def play_point(rules: dict[str, Any], state: dict[str, Any], winner: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """The state after `winner` wins one point, and facts about that point for the action."""
    if state["server"] not in (1, 2):
        raise FixtureError("a point is played from a state with no server")
    s = json.loads(json.dumps({k: state[k] for k in STATE_KEYS}))
    cur = current_set(s)
    server = s["server"]
    facts: dict[str, Any] = {"set": cur + 1, "server": server, "tiebreak": s["is_tiebreak"],
                             "set_tiebreak": None}
    facts["game"] = 1 if is_match_tiebreak(rules, cur) else s["games"][0][cur] + s["games"][1][cur] + 1
    set_over = False

    if s["is_tiebreak"]:
        first = tiebreak_first_server(s)
        count = [int(s["points"][0]), int(s["points"][1])]
        count[winner - 1] += 1
        target = 10 if is_match_tiebreak(rules, cur) else 7
        if is_match_tiebreak(rules, cur):
            s["games"][0][cur], s["games"][1][cur] = count
        if max(count) >= target and abs(count[0] - count[1]) >= 2:
            if not is_match_tiebreak(rules, cur):
                s["games"][winner - 1][cur] += 1
            facts["set_tiebreak"] = tuple(count)
            set_over = True
            s["server"] = other(first)
        else:
            s["points"] = [str(count[0]), str(count[1])]
            s["server"] = tiebreak_server(first, count[0] + count[1])
    else:
        mine, theirs = s["points"][winner - 1], s["points"][other(winner) - 1]
        ladder = {"0": "15", "15": "30", "30": "40"}
        game_won = False
        if mine in ladder:
            s["points"][winner - 1] = ladder[mine]
        elif mine == "40" and theirs in ladder:
            game_won = True
        elif mine == "40" and theirs == "40":
            if rules["no_ad"]:
                game_won = True
            else:
                s["points"][winner - 1] = "AD"
        elif mine == "40" and theirs == "AD":
            s["points"][other(winner) - 1] = "40"
        elif mine == "AD":
            game_won = True
        else:
            raise FixtureError(f"no legal point from {state['points']}")
        receiver = other(server)
        if game_won:
            facts["server_score"] = "game" if winner == server else GAME_WORD[state["points"][server - 1]]
            facts["receiver_score"] = "game" if winner == receiver else GAME_WORD[state["points"][receiver - 1]]
            s["games"][winner - 1][cur] += 1
            s["points"] = ["0", "0"]
            s["server"] = receiver
            g1, g2 = s["games"][0][cur], s["games"][1][cur]
            if set_won(rules, g1, g2):
                set_over = True
            elif g1 == g2 == rules["set_tiebreak_at"]:
                s["is_tiebreak"] = True
        else:
            facts["server_score"] = GAME_WORD[s["points"][server - 1]]
            facts["receiver_score"] = GAME_WORD[s["points"][receiver - 1]]

    if set_over:
        s["sets"][winner - 1] += 1
        s["points"] = ["0", "0"]
        s["is_tiebreak"] = False
        if s["sets"][winner - 1] == rules["best_of"] // 2 + 1:
            s["server"] = None
            facts["match_over"] = True
        else:
            s["games"][0].append(0)
            s["games"][1].append(0)
            s["is_tiebreak"] = is_match_tiebreak(rules, cur + 1)
    return s, facts


# --------------------------------------------------------------------------- the two forms


def attr(el: etree._Element | None, name: str) -> str | None:
    return None if el is None else el.get(name)


def check_fixture(name: str, schema: etree.XMLSchema) -> list[str]:
    fx = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    tree = parse_xml(FIXTURES / f"{name}.xml")
    notes = []

    if not schema.validate(tree):
        errors = "; ".join(f"line {e.line}: {e.message}" for e in schema.error_log)
        raise FixtureError(f"not valid against sportsml.xsd: {errors}")
    notes.append("valid against sportsml.xsd")

    root = tree.getroot()
    if fx.get("fixture") != name or fx.get("synthetic") is not True or fx.get("license") != "CC-BY-4.0":
        raise FixtureError("the JSON must name the fixture, say synthetic: true and carry CC-BY-4.0")
    title = root.findtext(f"{NS}sports-metadata/{NS}sports-title") or ""
    if not title.startswith("Synthetic fixture"):
        raise FixtureError("the SportsML sports-title must start with 'Synthetic fixture'")
    if "SYNTHETIC" not in "".join(c.text or "" for c in root.itersiblings(etree.Comment, preceding=True)):
        raise FixtureError("the SportsML document must open with the SYNTHETIC comment")

    rules, match, states = fx["rules"], fx["match"], fx["states"]
    event = root.find(f"{NS}sports-event")
    meta = event.find(f"{NS}event-metadata")
    tennis = meta.find(f"{NS}event-metadata-tennis")
    players = {p.get("id"): p for p in event.findall(f"{NS}player")}
    if set(players) != {"p1", "p2"}:
        raise FixtureError("the document needs players p1 and p2")
    for pid in ("p1", "p2"):
        want = match["players"][pid]["name"]
        got = players[pid].findtext(f"{NS}player-metadata/{NS}name")
        if got != want or "(synthetic)" not in want:
            raise FixtureError(f"{pid} is named {got!r}, the JSON says {want!r}; both must say (synthetic)")

    # Format and status.
    if attr(tennis, "number-of-sets") != str(FORMAT_SETS[match["format"]]):
        raise FixtureError("number-of-sets disagrees with format")
    if FORMAT_SETS[match["format"]] != rules["best_of"]:
        raise FixtureError("format disagrees with the fixture rules")
    status, reason, note = OUTCOME_STATUS[match["outcome"]]
    got = (meta.get("event-status"), meta.get("event-status-reason"), meta.get("event-status-note"))
    if got != (status, reason, note):
        raise FixtureError(f"outcome {match['outcome']} should be {(status, reason, note)}, the document has {got}")
    if match["status"] != "completed":
        raise FixtureError("every fixture is a finished match")
    if ("withdrew" in match) != (match["outcome"] in ("retired", "walkover")):
        raise FixtureError("withdrew is present exactly on a retirement or a walkover")
    if "withdrew" in match and match["withdrew"] != other(match["winner"]):
        raise FixtureError("the player who withdrew is the loser")
    for pid, num in (("p1", 1), ("p2", 2)):
        want = "speventoutcome:win" if match["winner"] == num else "speventoutcome:loss"
        if attr(players[pid].find(f"{NS}player-stats"), "event-outcome") != want:
            raise FixtureError(f"{pid} event-outcome should be {want}")
    notes.append(f"outcome {match['outcome']} = {status}" + (f" + {reason}" if reason else "")
                 + (f", note {note}" if note else ""))

    actions = event.findall(f"{NS}actions/{NS}action")
    if not states:
        if match["outcome"] != "walkover" or actions:
            raise FixtureError("only a walkover has no score states, and it has no actions")
        for pid in ("p1", "p2"):
            stats = players[pid].find(f"{NS}player-stats")
            if stats.get("score") is not None or len(stats):
                raise FixtureError("a walkover carries no score")
        notes.append("no states and no actions, as a walkover has none")
        return notes

    # Replay every point from the first state and compare with the JSON states.
    if len(actions) != len(states) - 1:
        raise FixtureError(f"{len(states)} states need {len(states) - 1} actions, the document has {len(actions)}")
    tiebreaks: dict[int, tuple[int, int]] = {}
    over = False
    for i, action in enumerate(actions):
        before, after = states[i], states[i + 1]
        roles = {}
        for part in action.findall(f"{NS}participant"):
            roles.setdefault(part.get("role"), []).append(part.get("idref"))
        try:
            (srv,), (rcv,), (won,) = roles["ltapirole:server"], roles["ltapirole:receiver"], roles["ltapirole:point-winner"]
        except (KeyError, ValueError):
            raise FixtureError(f"action {i + 1} needs one server, one receiver and one point-winner") from None
        winner = int(won[1:])
        expected, facts = play_point(rules, before, winner)
        where = f"action {i + 1} (sequence {after['sequence']})"
        if {k: after[k] for k in STATE_KEYS} != expected:
            raise FixtureError(f"{where}: replay gives {expected}, the JSON state is "
                               f"{ {k: after[k] for k in STATE_KEYS} }")
        if after["sequence"] != before["sequence"] + 1:
            raise FixtureError(f"{where}: sequence must rise by one")
        if action.get("sequence-number") != str(after["sequence"]):
            raise FixtureError(f"{where}: sequence-number disagrees with the state's sequence")
        if action.get("created") != after["accepted_at"]:
            raise FixtureError(f"{where}: created disagrees with accepted_at")
        if not before["accepted_at"] < after["accepted_at"]:
            raise FixtureError(f"{where}: accepted_at must rise")
        if action.get("type") != "sptenaction:point":
            raise FixtureError(f"{where}: type must be sptenaction:point")
        if (srv, rcv) != (f"p{facts['server']}", f"p{other(facts['server'])}"):
            raise FixtureError(f"{where}: server and receiver disagree with the state's server")
        if (action.get("set"), action.get("game")) != (str(facts["set"]), str(facts["game"])):
            raise FixtureError(f"{where}: set and game should be {facts['set']} and {facts['game']}")
        scores = (action.get("server-score"), action.get("receiver-score"))
        if facts["tiebreak"]:
            if scores != (None, None):
                raise FixtureError(f"{where}: a tie-break point has no sptengameresult code")
        elif scores != (f"sptengameresult:{facts['server_score']}", f"sptengameresult:{facts['receiver_score']}"):
            raise FixtureError(f"{where}: server-score and receiver-score should be "
                               f"{facts['server_score']} and {facts['receiver_score']}")
        if facts["set_tiebreak"]:
            tiebreaks[facts["set"] - 1] = facts["set_tiebreak"]
        over = bool(facts.get("match_over"))
        if over and i != len(actions) - 1:
            raise FixtureError(f"{where}: the match is over before the last action")
    notes.append(f"{len(actions)} points replayed from sequence {states[0]['sequence']}, "
                 f"every state matches the JSON")

    # The result in the document against the last state.
    last = states[-1]
    if match["outcome"] == "completed":
        if not over:
            raise FixtureError("a completed match must end on its last point")
        if match["winner"] != (1 if last["sets"][0] > last["sets"][1] else 2):
            raise FixtureError("winner disagrees with sets")
        if tennis.get("set") is not None:
            raise FixtureError("a finished match states no set in play")
    else:
        if over:
            raise FixtureError(f"a {match['outcome']} ends before the match is decided")
        cur = current_set(last)
        srv = last["server"]
        want = {"set": str(cur + 1), "game": str(last["games"][0][cur] + last["games"][1][cur] + 1),
                "server-idref": f"p{srv}", "receiver-idref": f"p{other(srv)}",
                "server-score": GAME_WORD[last["points"][srv - 1]],
                "receiver-score": GAME_WORD[last["points"][other(srv) - 1]]}
        got = {k: tennis.get(k) for k in want}
        if got != want:
            raise FixtureError(f"event-metadata-tennis should say where play stopped: {want}, has {got}")
        notes.append(f"play stopped at set {want['set']}, game {want['game']}, "
                     f"{want['server-score']}-{want['receiver-score']} on p{srv}'s serve")
    for num, pid in ((1, "p1"), (2, "p2")):
        stats = players[pid].find(f"{NS}player-stats")
        if stats.get("score") != str(last["sets"][num - 1]):
            raise FixtureError(f"{pid} score should be {last['sets'][num - 1]} sets")
        rows = stats.findall(f"{NS}player-stats-tennis/{NS}stats-tennis-set")
        if [r.get("set-number") for r in rows] != [str(n + 1) for n in range(len(last["games"][0]))]:
            raise FixtureError(f"{pid} needs one stats-tennis-set per set, numbered from 1")
        for n, row in enumerate(rows):
            tb = tiebreaks.get(n)
            if tb and is_match_tiebreak(rules, n):
                games = 1 if tb[num - 1] > tb[other(num) - 1] else 0
            else:
                games = last["games"][num - 1][n]
            if row.get("score") != str(games):
                raise FixtureError(f"{pid} set {n + 1} score should be {games}")
            if row.get("score-tiebreaker") != (str(tb[num - 1]) if tb else None):
                raise FixtureError(f"{pid} set {n + 1} score-tiebreaker disagrees with the replayed tie-break")
    sets_text = " ".join(
        (f"[{tiebreaks[n][0]}-{tiebreaks[n][1]}]" if n in tiebreaks and is_match_tiebreak(rules, n)
         else f"{last['games'][0][n]}-{last['games'][1][n]}" + (f"({min(tiebreaks[n])})" if n in tiebreaks else ""))
        for n in range(len(last["games"][0])))
    notes.append(f"result agrees: sets {last['sets'][0]}-{last['sets'][1]}, {sets_text}")
    return notes


def main() -> int:
    try:
        schema = load_schema()
    except FixtureError as exc:
        print(f"FAIL schema: {exc}")
        return 1
    print(f"IPTC SportsML 3.1 schema: {len(PINNED)} files match their pinned SHA-256")
    found = sorted(p.stem for p in FIXTURES.glob("*.json"))
    failed = 0
    if found != EXPECTED or sorted(p.stem for p in FIXTURES.glob("*.xml")) != EXPECTED:
        print(f"FAIL fixtures: expected {EXPECTED}, found {found}")
        failed += 1
    for name in EXPECTED:
        try:
            notes = check_fixture(name, schema)
        except (FixtureError, OSError, ValueError, KeyError, etree.XMLSyntaxError) as exc:
            print(f"FAIL {name}: {exc}")
            failed += 1
            continue
        print(f"ok   {name}")
        for note in notes:
            print(f"     {note}")
    if failed:
        print(f"{failed} problem(s)")
        return 1
    print(f"All {len(EXPECTED)} fixtures pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
