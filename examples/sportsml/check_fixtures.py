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
from datetime import datetime
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

# Match.outcome -> (event-status, event-status-reason, event-status-note, event-outcome-type) in the
# SportsML document.
OUTCOME_STATUS = {
    "completed": ("speventstatus:post-event", None, None, None),
    "retired": ("speventstatus:forfeited", "speventstatusreason:withdrawal", "retired", None),
    "walkover": ("speventstatus:forfeited", "speventstatusreason:withdrawal", "walkover", None),
    "default": ("speventstatus:forfeited", None, "default", "speventoutcometype:authority-decision"),
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
    """A finished set: 6-0 to 6-4, 7-5, or 7-6 after the tie-break."""
    at = rules["set_tiebreak_at"]
    high, low = max(g1, g2), min(g1, g2)
    return (high == at and low <= at - 2) or (high == at + 1 and low in (at - 1, at))


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


STATE_FIELDS = ["sets", "games", "points", "server", "is_tiebreak", "timestamp", "accepted_at", "sequence"]
POINT_WORDS = ("0", "15", "30", "40", "AD")


def check_rules(rules: dict[str, Any]) -> None:
    if (rules.get("best_of") not in (3, 5) or not isinstance(rules.get("no_ad"), bool)
            or rules.get("set_tiebreak_at") != 6
            or rules.get("final_set") not in ("tiebreak", "match_tiebreak")):
        raise FixtureError("rules need best_of 3 or 5, a boolean no_ad, set_tiebreak_at 6 and "
                           "final_set tiebreak or match_tiebreak")


def check_start(rules: dict[str, Any], s: dict[str, Any]) -> None:
    """The first state is a legal score: finished sets won, the set in play open, legal points."""
    games, sets = s["games"], s["sets"]
    need = rules["best_of"] // 2 + 1
    if len(games) != 2 or len(games[0]) != len(games[1]) or len(sets) != 2:
        raise FixtureError("the first state needs two sets counts and two per-set games lists of one length")
    cur = len(games[0]) - 1
    won = [0, 0]
    for n in range(cur):
        g1, g2 = games[0][n], games[1][n]
        if is_match_tiebreak(rules, n) or not set_won(rules, g1, g2):
            raise FixtureError(f"set {n + 1} of the first state, {g1}-{g2}, is not a finished set")
        won[0 if g1 > g2 else 1] += 1
    if won != sets or max(sets) >= need or cur >= rules["best_of"]:
        raise FixtureError("the first state's sets disagree with its finished sets, or the match is over")
    g1, g2 = games[0][cur], games[1][cur]
    if s["server"] not in (1, 2):
        raise FixtureError("the first state needs a server")
    if is_match_tiebreak(rules, cur):
        tb_expected = True
    else:
        if set_won(rules, g1, g2) or max(g1, g2) > rules["set_tiebreak_at"]:
            raise FixtureError(f"the set in play, {g1}-{g2}, is already over")
        tb_expected = g1 == g2 == rules["set_tiebreak_at"]
    if s["is_tiebreak"] != tb_expected:
        raise FixtureError("is_tiebreak disagrees with the games in the set in play")
    a, b = s["points"]
    if tb_expected:
        if not (a.isdigit() and b.isdigit()):
            raise FixtureError("tie-break points must be counts")
        target = 10 if is_match_tiebreak(rules, cur) else 7
        if max(int(a), int(b)) >= target and abs(int(a) - int(b)) >= 2:
            raise FixtureError("the tie-break in the first state is already over")
        if is_match_tiebreak(rules, cur) and [g1, g2] != [int(a), int(b)]:
            raise FixtureError("a match tie-break's games slot must equal its points")
    elif a not in POINT_WORDS or b not in POINT_WORDS or (
            "AD" in (a, b) and (rules["no_ad"] or {a, b} != {"AD", "40"})):
        raise FixtureError(f"{[a, b]} is not a legal game score")


# --------------------------------------------------------------------------- the two forms


def instant(text: str) -> datetime:
    """An RFC 3339 UTC time such as 2026-01-05T10:00:40Z, compared as a time and not as text."""
    if not text.endswith("Z"):
        raise FixtureError(f"{text!r} must be UTC with a Z")
    return datetime.fromisoformat(text[:-1] + "+00:00")


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
    check_rules(rules)
    for state in states:
        if list(state) != STATE_FIELDS or state["timestamp"] != state["accepted_at"]:
            raise FixtureError(f"state {state.get('sequence')} needs the fields {STATE_FIELDS}, "
                               "with timestamp equal to accepted_at")
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
    want_status = OUTCOME_STATUS[match["outcome"]]
    status, reason, note, outcome_type = want_status
    got = tuple(meta.get(a) for a in ("event-status", "event-status-reason", "event-status-note",
                                      "event-outcome-type"))
    if got != want_status:
        raise FixtureError(f"outcome {match['outcome']} should be {want_status}, the document has {got}")
    if match["status"] != "completed":
        raise FixtureError("every fixture is a finished match")
    if ("withdrew" in match) != (match["outcome"] in ("retired", "walkover")):
        raise FixtureError("withdrew is present exactly on a retirement or a walkover")
    if match["winner"] not in (1, 2):
        raise FixtureError("winner must be 1 or 2")
    if "withdrew" in match and match["withdrew"] != other(match["winner"]):
        raise FixtureError("the player who withdrew is the loser")
    for pid, num in (("p1", 1), ("p2", 2)):
        want = "speventoutcome:win" if match["winner"] == num else "speventoutcome:loss"
        if attr(players[pid].find(f"{NS}player-stats"), "event-outcome") != want:
            raise FixtureError(f"{pid} event-outcome should be {want}")
    notes.append(f"outcome {match['outcome']} = {status}" + (f" + {reason}" if reason else "")
                 + (f" + {outcome_type}" if outcome_type else "") + (f", note {note}" if note else ""))

    actions = event.findall(f"{NS}actions/{NS}action")
    if match["outcome"] == "walkover" and states:
        raise FixtureError("a walkover has no score states: no ball was struck")
    if not states:
        if match["outcome"] != "walkover" or actions:
            raise FixtureError("only a walkover has no score states, and it has no actions")
        for pid in ("p1", "p2"):
            stats = players[pid].find(f"{NS}player-stats")
            if stats.get("score") is not None or len(stats):
                raise FixtureError("a walkover carries no score")
        notes.append("no states and no actions, as a walkover has none")
        return notes

    check_start(rules, states[0])
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
        if {srv, rcv, won} - {"p1", "p2"} or srv == rcv:
            raise FixtureError(f"action {i + 1}: participants must be the players p1 and p2")
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
        if not instant(before["accepted_at"]) < instant(after["accepted_at"]):
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
        if set(tennis.attrib) != {"number-of-sets"}:
            raise FixtureError("a finished match states no set, game, server or score in play")
    else:
        if over:
            raise FixtureError(f"a {match['outcome']} ends before the match is decided")
        cur = current_set(last)
        srv = last["server"]
        game = 1 if is_match_tiebreak(rules, cur) else last["games"][0][cur] + last["games"][1][cur] + 1
        want = {"set": str(cur + 1), "game": str(game),
                "server-idref": f"p{srv}", "receiver-idref": f"p{other(srv)}"}
        if not last["is_tiebreak"]:
            # A tie-break count has no gameResult.Tennis value, so a stop inside one has no score here.
            want["server-score"] = GAME_WORD[last["points"][srv - 1]]
            want["receiver-score"] = GAME_WORD[last["points"][other(srv) - 1]]
        got = {k: v for k, v in tennis.attrib.items() if k != "number-of-sets"}
        if got != want:
            raise FixtureError(f"event-metadata-tennis should say where play stopped: {want}, has {got}")
        score = (f"{want['server-score']}-{want['receiver-score']}" if "server-score" in want
                 else "in a tie-break")
        notes.append(f"play stopped at set {want['set']}, game {want['game']}, {score} on p{srv}'s serve")
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
        except FixtureError as exc:
            print(f"FAIL {name}: {exc}")
            failed += 1
            continue
        except Exception as exc:  # a malformed fixture fails alone; the others are still checked
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
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
