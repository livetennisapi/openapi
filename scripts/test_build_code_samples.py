"""Tests for build_code_samples.py. Run: python -m unittest scripts/test_build_code_samples.py

Each test breaks a copy of the spec or the method map and checks that the
check fails with the right message. The real files are never written.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_code_samples as bcs  # noqa: E402


class CheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.spec_text = bcs.SPEC.read_text(encoding="utf-8")
        self.methods = bcs.load_methods()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_check(self, spec_text: str | None = None, methods: dict | None = None) -> list[str]:
        spec = self.dir / "openapi.yaml"
        spec.write_text(self.spec_text if spec_text is None else spec_text, encoding="utf-8")
        mapping = self.dir / "sdk-methods.yaml"
        mapping.write_text(yaml.safe_dump(self.methods if methods is None else methods), encoding="utf-8")
        return bcs.check(spec, mapping)

    def test_the_committed_spec_is_current(self) -> None:
        self.assertEqual(self.run_check(), [])

    def test_an_operation_with_no_entry_fails(self) -> None:
        del self.methods["operations"]["getMatch"]
        found = "\n".join(self.run_check())
        self.assertIn("operation 'getMatch' is in the spec but has no entry", found)

    def test_an_entry_for_an_unknown_operation_fails(self) -> None:
        self.methods["operations"]["getNothing"] = {"result": "nothing"}
        found = "\n".join(self.run_check())
        self.assertIn("names operation 'getNothing', which the spec does not define", found)

    def test_a_changed_call_makes_the_spec_stale(self) -> None:
        self.methods["operations"]["getMatch"]["python"] = "get_match(1)"
        found = "\n".join(self.run_check())
        self.assertIn("are stale", found)

    def test_a_hand_edit_to_a_sample_makes_the_spec_stale(self) -> None:
        edited = self.spec_text.replace("match = client.get_match(18953)", "match = client.get_match(1)", 1)
        self.assertNotEqual(edited, self.spec_text)
        self.assertIn("are stale", "\n".join(self.run_check(spec_text=edited)))

    def test_a_missing_path_parameter_value_fails(self) -> None:
        del self.methods["operations"]["getMatch"]["params"]["matchId"]
        found = "\n".join(self.run_check())
        self.assertIn("getMatch: params has no value for the required parameter 'matchId'", found)

    def test_an_undeclared_parameter_fails(self) -> None:
        self.methods["operations"]["getMatch"]["params"]["nope"] = 1
        self.assertIn("params names 'nope'", "\n".join(self.run_check()))

    def test_an_unknown_client_key_fails(self) -> None:
        self.methods["operations"]["getMatch"]["ruby"] = "get_match(18953)"
        self.assertIn("getMatch: unknown key 'ruby'", "\n".join(self.run_check()))

    def test_stripping_and_writing_again_gives_the_same_text(self) -> None:
        stripped = bcs.strip_blocks(self.spec_text)
        self.assertNotIn("x-codeSamples", stripped)
        self.assertEqual(bcs.generate(stripped, self.methods), self.spec_text)

    def test_a_client_without_a_method_gets_no_sample(self) -> None:
        spec = yaml.safe_load(self.spec_text)
        samples = bcs.build_samples(spec, self.methods)
        labels = [s["label"] for s in samples["getUsage"]]
        self.assertNotIn("JavaScript", labels)
        self.assertEqual([s["label"] for s in samples["listSlateEvents"]], ["curl"])

    def test_no_sample_holds_a_literal_key(self) -> None:
        spec = yaml.safe_load(self.spec_text)
        for oid, samples in bcs.build_samples(spec, self.methods).items():
            for sample in samples:
                self.assertNotIn("twjp_", sample["source"], f"{oid} {sample['label']}")
                if oid != "healthCheck":  # /health takes no key
                    self.assertIn("LIVETENNISAPI_KEY", sample["source"], f"{oid} {sample['label']}")


if __name__ == "__main__":
    unittest.main()
