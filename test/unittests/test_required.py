"""Every shipped locale pairs wiki.intent and wikiroulette.intent with a
.required file (OVOS-INTENT-2 §4.5), and each golden positive for those
intents names one of the required keywords."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCALE = ROOT / "ovos_skill_wikipedia" / "locale"
GOLDEN = ROOT / "test" / "end2end"
INTENTS = ("wiki", "wikiroulette")
# Golden rows whose template carries no service word; the intent rejects them
# once an engine applies .required. The set must shrink as the rows are fixed.
UNANCHORED_ROWS = {
    ("de-DE", "Erzähl mir von pizza"),
    ("de-DE", "Erzähl mir von yoga"),
    ("sv-SE", "spela roulette"),
}


def _keywords(path):
    return [ln.strip().lower() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


def _occurs(keyword, utterance):
    return re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", utterance.lower()) is not None


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
                if not any(_occurs(k, row["utterance"]) for k in keywords):
                    unanchored.add((row["lang"], row["utterance"]))
                checked += 1
        self.assertEqual(unanchored, UNANCHORED_ROWS)
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
