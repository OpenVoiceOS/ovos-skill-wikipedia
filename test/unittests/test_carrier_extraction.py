"""The carrier phrasings must still return the RIGHT article.

`Erzähl mir von {query}` used to be a line of `wiki.intent`, and the intent
match was the only stage that separated the carrier from the subject: the
handler received {query}="pizza" and searched THAT. With the line removed the
phrasing reaches the common query whole, and the real engine answers:

    search("pizza")                -> "Pizza"
    search("Erzähl mir von pizza") -> "All das Ungesagte zwischen uns – Regretting You"

A novel. So "the common query still claims it" is not the same as "the user
gets the right article", and only a test that names the expected TITLE can tell
the two apart.

These hit the real Wikipedia API. A network failure skips rather than fails:
a red build on somebody else's outage teaches nothing, and the assertion is
about our extraction, not about the API being up.
"""
import os
import unittest
from types import SimpleNamespace

from ovos_wikipedia import WikipediaRetrievalEngine

import ovos_skill_wikipedia as module
from ovos_skill_wikipedia import WikipediaSkill

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# utterance, lang, the subject the carrier wraps, the article it must find
CASES = [
    ("Erzähl mir von pizza", "de-DE", "pizza", "Pizza"),
    ("Erzähl uns von Kaffee", "de-DE", "Kaffee", "Kaffee"),
    ("расскажи мне о Москве", "ru-RU", "Москве", "Москва"),
    ("поведай мне о Москве", "ru-RU", "Москве", "Москва"),
]


def _extractor():
    fake = SimpleNamespace(_template_cache={})
    fake._query_templates = lambda lang: WikipediaSkill._query_templates(fake, lang)
    return lambda utterance, lang: WikipediaSkill.extract_subject(fake, utterance, lang)


class TestCarrierExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module.__file__ = os.path.join(SKILL_DIR, "ovos_skill_wikipedia",
                                       "__init__.py")
        cls.extract = staticmethod(_extractor())
        cls.engine = WikipediaRetrievalEngine({})

    def _search(self, text, lang):
        try:
            return self.engine.search(text, lang=lang.split("-")[0])
        except Exception as exc:  # network, rate limit, API change
            self.skipTest(f"wikipedia unreachable: {type(exc).__name__}: {exc}")

    def test_every_removed_form_yields_its_subject(self):
        """Offline: the extraction itself, with no network involved."""
        for utterance, lang, subject, _ in CASES:
            with self.subTest(utterance=utterance):
                self.assertEqual(subject, self.extract(utterance, lang))

    def test_every_removed_form_finds_the_right_article(self):
        for utterance, lang, _, title in CASES:
            with self.subTest(utterance=utterance):
                results = self._search(self.extract(utterance, lang), lang)
                self.assertTrue(results, f"{utterance!r} found nothing")
                self.assertEqual(
                    title, results[0].title,
                    f"{utterance!r} returned {results[0].title!r}, not "
                    f"{title!r}")

    def test_the_carrier_is_what_breaks_the_search(self):
        """The control: without extraction these return the WRONG article.

        Without it, the test above could pass against an engine that ignores
        the carrier anyway, and would not show that the extraction is what
        fixed anything.
        """
        wrong = []
        for utterance, lang, _, title in CASES:
            results = self._search(utterance, lang)
            if not results or results[0].title != title:
                wrong.append(utterance)
        self.assertEqual(
            [u for u, _, _, _ in CASES], wrong,
            "a carrier phrase found the right article WITHOUT extraction, so "
            "this suite is not measuring what it claims")

    def test_an_uncovered_phrasing_passes_through_unchanged(self):
        for utterance, lang in (("pizza", "de-DE"), ("Москва", "ru-RU"),
                                ("was ist ein Pangolin", "de-DE")):
            with self.subTest(utterance=utterance):
                self.assertEqual(utterance, self.extract(utterance, lang))


class TestDoubledSpacesInsideTheCarrier(unittest.TestCase):
    """A doubled space between the carrier's own words must still match.

    `re.escape` on the whole carrier made each internal space one literal
    space, so "Erzähl  mir  von pizza" matched nothing and passed through
    unchanged, which sends the carrier phrase to the search and finds the
    wrong article. Doubling AROUND the carrier always worked: the pattern's
    own `\\s+` absorbs it.
    """

    @classmethod
    def setUpClass(cls):
        module.__file__ = os.path.join(SKILL_DIR, "ovos_skill_wikipedia",
                                       "__init__.py")
        cls.extract = staticmethod(_extractor())

    def test_a_doubled_space_inside_the_carrier(self):
        self.assertEqual("pizza",
                         self.extract("Erzähl  mir  von pizza", "de-DE"))

    def test_a_single_space_carrier_still_matches(self):
        """The control: the case that already worked must not move."""
        self.assertEqual("pizza",
                         self.extract("Erzähl mir von pizza", "de-DE"))

    def test_a_phrasing_with_no_carrier_is_still_unchanged(self):
        """The control in the other direction: the default is passthrough."""
        self.assertEqual("pizza", self.extract("pizza", "de-DE"))


if __name__ == "__main__":
    unittest.main()
