"""Every shipped locale pairs wiki.intent and wikiroulette.intent with a
.required file (OVOS-INTENT-2 §4.5). Each expanded template line and each
golden positive for those intents names one of the required keywords, so no
line is one the intent always rejects."""
import json
import unittest
from pathlib import Path

from ovos_spec_tools import expand, utterance_contains

ROOT = Path(__file__).resolve().parents[2]
LOCALE = ROOT / "ovos_skill_wikipedia" / "locale"
GOLDEN = ROOT / "test" / "end2end"
INTENTS = ("wiki", "wikiroulette")


def _lines(path):
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


def _keywords(path):
    return [kw.lower() for ln in _lines(path) for kw in expand(ln)]


class TestRequiredKeywords(unittest.TestCase):
    def test_every_locale_with_the_intent_has_keywords(self):
        checked = 0
        for intent_file in sorted(LOCALE.glob("*/*.intent")):
            name = intent_file.stem
            if name not in INTENTS:
                continue
            required = intent_file.with_suffix(".required")
            with self.subTest(locale=intent_file.parent.name, intent=name):
                self.assertTrue(required.is_file(), f"missing {required}")
                self.assertTrue(_keywords(required), f"empty {required}")
            checked += 1
        self.assertGreater(checked, 0)

    def test_golden_positives_name_a_keyword(self):
        checked = 0
        unanchored = set()
        for golden in sorted(GOLDEN.glob("golden_utterances_*.jsonl")):
            for line in golden.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                intent = row["intent_label"].removesuffix(".intent")
                if intent not in INTENTS:
                    continue
                required = LOCALE / row["lang"] / f"{intent}.required"
                keywords = _keywords(required) if required.is_file() else []
                if not utterance_contains(row["utterance"], keywords):
                    unanchored.add((row["lang"], row["utterance"]))
                checked += 1
        self.assertEqual(unanchored, set())
        self.assertGreater(checked, 0)

    def test_every_template_line_names_a_keyword(self):
        checked = 0
        unanchored = set()
        for intent_file in sorted(LOCALE.glob("*/*.intent")):
            if intent_file.stem not in INTENTS:
                continue
            keywords = _keywords(intent_file.with_suffix(".required"))
            for line in _lines(intent_file):
                for sample in expand(line):
                    if not utterance_contains(sample, keywords):
                        unanchored.add((intent_file.parent.name, sample))
                    checked += 1
        self.assertEqual(unanchored, set())
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
