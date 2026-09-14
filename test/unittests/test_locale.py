"""
Tests for the en-US intent definitions and the {query} pronoun slot-value
exclusion (OVOS-INTENT-2 §4.3).
"""
import os
import re
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


# Every brand this skill's voc_blacklist names, and the entry the file
# must list. The brand names are the same in every language, so the file
# is identical in each locale.
BRAND_VOCS = (("wikihow.voc", "wikihow"), ("wordnet.voc", "wordnet"))


class TestBrandBlacklistParity(unittest.TestCase):
    """``wiki.intent`` carries the generic templates "search wiki for
    {query}" and "what does the wiki say about {query}", which padatious
    sometimes matches against "search wikihow for something" and "ask
    wordnet about word". ``voc_blacklist`` suppresses that, but only in a
    locale that ships the voc file: a missing file makes the blacklist
    silently do nothing. So every locale with the intent must ship every
    brand file."""

    def _locales_with_wiki_intent(self):
        return sorted(
            d for d in os.listdir(LOCALE_ROOT)
            if os.path.isfile(os.path.join(LOCALE_ROOT, d, "wiki.intent"))
        )

    def test_every_locale_with_the_intent_ships_the_voc(self):
        for voc, _brand in BRAND_VOCS:
            missing = [
                d for d in self._locales_with_wiki_intent()
                if not os.path.isfile(os.path.join(LOCALE_ROOT, d, voc))
            ]
            self.assertEqual(missing, [], f"{voc} missing in: {missing}")

    def test_the_voc_names_the_brand(self):
        for voc, brand in BRAND_VOCS:
            for d in self._locales_with_wiki_intent():
                with open(os.path.join(LOCALE_ROOT, d, voc)) as f:
                    entries = {ln.strip().lower() for ln in f if ln.strip()}
                self.assertIn(brand, entries, f"{d}: {brand} not listed")

    def test_the_handler_blacklists_every_brand(self):
        """A voc file that the handler does not name does nothing."""
        src = os.path.join(
            os.path.dirname(LOCALE_ROOT), "__init__.py")
        with open(src) as f:
            text = f.read()
        match = re.search(r"voc_blacklist=\[([^\]]*)\]", text)
        self.assertIsNotNone(match, "no voc_blacklist on the handler")
        listed = {v.strip().strip('"\'') for v in match.group(1).split(",")}
        for _voc, brand in BRAND_VOCS:
            self.assertIn(brand, listed,
                          f"{brand} not in the handler voc_blacklist")


if __name__ == "__main__":
    unittest.main()
