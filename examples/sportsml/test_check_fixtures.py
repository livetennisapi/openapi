"""Tests for check_fixtures.py: the real fixtures pass and broken copies fail.

Each test copies this folder into a temporary directory, breaks one thing and runs the checker
there. Run with:
    pip install lxml
    python -m unittest examples/sportsml/test_check_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class CheckFixturesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "sportsml"
        shutil.copytree(HERE, self.root, ignore=shutil.ignore_patterns("__pycache__"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_check(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-I", str(self.root / "check_fixtures.py")],
                              capture_output=True, text=True, check=False)

    def edit(self, name: str, old: str, new: str) -> None:
        path = self.root / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"{old!r} not in {name}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def assert_fails(self, needle: str) -> None:
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(needle, result.stdout)

    def test_fixtures_pass(self) -> None:
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("All 6 fixtures pass", result.stdout)

    def test_changed_schema_file_is_refused(self) -> None:
        path = self.root / "iptc-sportsml-3.1" / "sportsml-specific-tennis.xsd"
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_fails("differs from the IPTC file")

    def test_schema_violation(self) -> None:
        self.edit("fixtures/03-no-ad.xml", 'set="2" game="9"', 'set="two" game="9"')
        self.assert_fails("not valid against sportsml.xsd")

    def test_doctype_is_refused(self) -> None:
        self.edit("fixtures/04-retirement.xml", '<?xml version="1.0" encoding="UTF-8"?>',
                  '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE sports-content [<!ENTITY x "y">]>')
        self.assert_fails("DOCTYPE is not allowed")

    def test_wrong_point_winner(self) -> None:
        # The first point of the retirement fixture goes to p1. Give it to p2 in the XML only.
        self.edit("fixtures/04-retirement.xml", '<participant idref="p1" role="ltapirole:point-winner"/>',
                  '<participant idref="p2" role="ltapirole:point-winner"/>')
        self.assert_fails("replay gives")

    def test_advantage_in_a_no_ad_game(self) -> None:
        path = self.root / "fixtures" / "03-no-ad.json"
        fx = json.loads(path.read_text(encoding="utf-8"))
        fx["rules"]["no_ad"] = False
        path.write_text(json.dumps(fx), encoding="utf-8")
        self.assert_fails("replay gives")

    def test_tiebreak_score_must_agree(self) -> None:
        self.edit("fixtures/01-deciding-set-tiebreak.xml", 'score-tiebreaker="9"', 'score-tiebreaker="7"')
        self.assert_fails("score-tiebreaker disagrees")

    def test_outcome_codes(self) -> None:
        self.edit("fixtures/06-default.xml", 'event-status-note="default"', 'event-status-note="retired"')
        self.assert_fails("outcome default should be")

    def test_synthetic_label(self) -> None:
        self.edit("fixtures/02-match-tiebreak.json", '"name": "Player A (synthetic)"', '"name": "Player A"')
        self.assert_fails("must say (synthetic)")

    def test_sequence_must_match(self) -> None:
        self.edit("fixtures/02-match-tiebreak.xml", 'sequence-number="305"', 'sequence-number="350"')
        self.assert_fails("sequence-number disagrees")

    def test_first_state_must_be_legal(self) -> None:
        # Player A won the first set 6-3, so sets [0, 1] is wrong in every state. The replay alone
        # would not notice, because each point still moves the score correctly.
        path = self.root / "fixtures" / "04-retirement.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"sets": [1, 0]', '"sets": [0, 1]'),
                        encoding="utf-8")
        self.edit("fixtures/04-retirement.xml", '<player-stats score="1"', '<player-stats score="X"')
        self.edit("fixtures/04-retirement.xml", '<player-stats score="0"', '<player-stats score="1"')
        self.edit("fixtures/04-retirement.xml", '<player-stats score="X"', '<player-stats score="0"')
        self.assert_fails("disagree with its finished sets")

    def test_unfinished_first_set(self) -> None:
        path = self.root / "fixtures" / "01-deciding-set-tiebreak.json"
        path.write_text(path.read_text(encoding="utf-8").replace("[4, 6, 6]]", "[5, 6, 6]]"),
                        encoding="utf-8")
        self.assert_fails("is not a finished set")

    def test_timestamp_must_equal_accepted_at(self) -> None:
        self.edit("fixtures/02-match-tiebreak.json", '"timestamp": "2026-01-05T10:02:00Z"',
                  '"timestamp": "1999-01-01T00:00:00Z"')
        self.assert_fails("timestamp equal to accepted_at")

    def test_finished_match_has_no_state_in_play(self) -> None:
        self.edit("fixtures/01-deciding-set-tiebreak.xml", '<event-metadata-tennis number-of-sets="3"/>',
                  '<event-metadata-tennis game="13" number-of-sets="3"/>')
        self.assert_fails("states no set, game, server or score in play")

    def test_rules_are_validated(self) -> None:
        self.edit("fixtures/04-retirement.json", '"final_set": "tiebreak"', '"final_set": "advantage"')
        self.assert_fails("rules need")

    def test_a_broken_fixture_fails_alone(self) -> None:
        path = self.root / "fixtures" / "04-retirement.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"games": [[6, 2], [3, 1]]', '"games": [[6, 2], [3]]', 1),
                        encoding="utf-8")
        result = self.run_check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("FAIL 04-retirement", result.stdout)
        self.assertIn("ok   06-default", result.stdout)

    def test_impossible_finished_set(self) -> None:
        path = self.root / "fixtures" / "04-retirement.json"
        path.write_text(path.read_text(encoding="utf-8").replace("[[6, 2], [3, 1]]", "[[7, 2], [3, 1]]"),
                        encoding="utf-8")
        self.edit("fixtures/04-retirement.xml", 'set-number="1" score="6"', 'set-number="1" score="7"')
        self.assert_fails("is not a finished set")

    def test_walkover_with_points(self) -> None:
        path = self.root / "fixtures" / "04-retirement.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"outcome": "retired"', '"outcome": "walkover"'),
                        encoding="utf-8")
        self.edit("fixtures/04-retirement.xml", 'event-status-note="retired"', 'event-status-note="walkover"')
        self.assert_fails("a walkover has no score states")

    def test_participants_must_be_players(self) -> None:
        self.edit("fixtures/04-retirement.xml", '<participant idref="p1" role="ltapirole:point-winner"/>',
                  '<participant idref="p2" role="ltapirole:point-winner"/>')
        self.edit("fixtures/04-retirement.xml", '<participant idref="p2" role="ltapirole:server"/>',
                  '<participant idref="p2" role="ltapirole:server"/><participant idref="p2" role="ltapirole:spare"/>')
        self.edit("fixtures/04-retirement.xml", 'set="2" game="4" server-score="sptengameresult:love"',
                  'id="x1" set="2" game="4" server-score="sptengameresult:love"')
        self.edit("fixtures/04-retirement.xml", '<participant idref="p2" role="ltapirole:point-winner"/>',
                  '<participant idref="x1" role="ltapirole:point-winner"/>')
        self.assert_fails("participants must be the players")

    def test_time_must_rise(self) -> None:
        path = self.root / "fixtures" / "04-retirement.json"
        text = path.read_text(encoding="utf-8").replace("10:00:00Z", "10:00:40.900Z")
        path.write_text(text, encoding="utf-8")
        self.assert_fails("accepted_at must rise")

    def test_missing_fixture(self) -> None:
        (self.root / "fixtures" / "05-walkover.json").unlink()
        self.assert_fails("FAIL fixtures")


if __name__ == "__main__":
    unittest.main()
