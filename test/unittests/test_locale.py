"""
Tests for the en-US intent definitions and the {query} pronoun slot-value
exclusion (OVOS-INTENT-2 §4.3).
"""
import os
import unittest

from ovos_spec_tools import expand

LOCALE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "ovos_skill_wikipedia", "locale", "en-US",
)


def _lines(name):
    with open(os.path.join(LOCALE, name)) as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def _samples(name, vocabularies=None):
    out = []
    for line in _lines(name):
        out.extend(expand(line, vocabularies) if vocabularies else expand(line))
    return out


class TestIntentAnchoring(unittest.TestCase):
    """Every explicit template must mention wikipedia so the open {query}
    slot cannot swallow utterances another skill should own."""

    def test_every_wiki_sample_is_keyword_anchored(self):
        for sample in _samples("wiki.intent"):
            self.assertTrue(
                "wiki" in sample or "wikipedia" in sample,
                f"un-anchored template would over-grab: {sample!r}",
            )

    def test_every_roulette_sample_is_keyword_anchored(self):
        for sample in _samples("wikiroulette.intent"):
            self.assertTrue("wiki" in sample or "wikipedia" in sample, sample)

    def test_new_phrasings_present(self):
        samples = _samples("wiki.intent")
        self.assertIn("who is {query} on wiki", samples)
        self.assertIn("who was {query} on wikipedia", samples)
        self.assertIn("tell me about {query} on wiki", samples)


class TestPronounVocabulary(unittest.TestCase):
    """pronoun.voc lists the exact values WikipediaSkill._is_anaphoric
    rejects from the {query} slot (see test/unittests/test_skill.py for the
    exact-match-not-containment behavior)."""

    def _pronouns(self):
        return set(_samples("pronoun.voc"))

    def test_pronouns_and_demonstratives_present(self):
        pronouns = self._pronouns()
        for word in ("he", "she", "it", "they", "him", "her", "them",
                     "their", "that", "this", "those", "these"):
            self.assertIn(word, pronouns)

    def test_real_titles_not_listed(self):
        pronouns = self._pronouns()
        for title in ("ada lovelace", "python", "berlin",
                      "the it crowd", "her majesty"):
            self.assertNotIn(title, pronouns)


if __name__ == "__main__":
    unittest.main()
