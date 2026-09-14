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


LOCALE_ROOT = os.path.dirname(LOCALE)


class TestWikiBlacklistParity(unittest.TestCase):
    """``wiki.intent`` carries the generic template "search wiki for
    {query}", which padatious sometimes matches against another skill's
    brand ("search wikihow for something", "ask wordnet about word").
    OVOS-INTENT-2 §1 gives the suppression words their own role, and §4.3
    pairs the file with the intent by base name: ``wiki.blacklist`` beside
    ``wiki.intent``. A locale with the intent and no blacklist file
    suppresses nothing, in silence. The brand names are the same in every
    language, so every locale with the intent must ship the file."""

    BRANDS = ("wikihow", "wordnet")

    def _locales_with_wiki_intent(self):
        return sorted(
            d for d in os.listdir(LOCALE_ROOT)
            if os.path.isfile(os.path.join(LOCALE_ROOT, d, "wiki.intent"))
        )

    def _entries(self, lang):
        path = os.path.join(LOCALE_ROOT, lang, "wiki.blacklist")
        with open(path, encoding="utf-8") as f:
            return {ln.strip().lower() for ln in f if ln.strip()}

    def test_every_locale_with_the_intent_ships_the_blacklist(self):
        missing = [
            d for d in self._locales_with_wiki_intent()
            if not os.path.isfile(
                os.path.join(LOCALE_ROOT, d, "wiki.blacklist"))
        ]
        self.assertEqual(missing, [], f"wiki.blacklist missing in: {missing}")

    def test_the_blacklist_names_every_brand(self):
        for d in self._locales_with_wiki_intent():
            entries = self._entries(d)
            for brand in self.BRANDS:
                self.assertIn(brand, entries, f"{d}: {brand} not listed")

    def test_the_blacklist_keeps_the_local_weather_words(self):
        """The weather words move into the blacklist; the file they came
        from stays, because the common-query path still reads it."""
        for d in self._locales_with_wiki_intent():
            path = os.path.join(LOCALE_ROOT, d, "weather.voc")
            if not os.path.isfile(path):
                continue  # ru-RU ships no weather.voc; see the PR body
            with open(path, encoding="utf-8") as f:
                weather = {ln.strip().lower() for ln in f if ln.strip()}
            self.assertLessEqual(weather, self._entries(d), d)

    def test_the_per_brand_voc_files_are_gone(self):
        # the role replaces them; a leftover file is a second source of
        # truth that nothing reads
        left = [d for d in self._locales_with_wiki_intent()
                if os.path.isfile(os.path.join(LOCALE_ROOT, d, "wikihow.voc"))]
        self.assertEqual(left, [], f"wikihow.voc still present in: {left}")


if __name__ == "__main__":
    unittest.main()
