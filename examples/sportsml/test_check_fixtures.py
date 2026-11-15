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

    def test_missing_fixture(self) -> None:
        (self.root / "fixtures" / "05-walkover.json").unlink()
        self.assert_fails("FAIL fixtures")


if __name__ == "__main__":
    unittest.main()
