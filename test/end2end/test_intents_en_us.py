"""End-to-end intent-routing tests for the en-US Wikipedia skill.

Boots an in-process MiniCroft with the skill loaded and feeds it real
utterances, asserting where each one routes and how the {query} slot is
filled. The network lookup is stubbed so the suite is offline.
"""
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_spec_tools import canonical_intent_topic
from ovoscope import CaptureSession
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-wikipedia.openvoiceos"
LANG = "en-US"
WIKI = f"{SKILL_ID}:wiki"
WIKIROULETTE = f"{SKILL_ID}:wikiroulette"


class _RoutingTest(TestCase):
    """Shared MiniCroft harness with a stubbed Wikipedia backend."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_prototype_minicroft([SKILL_ID], lang=LANG)
        cls.skill = cls.minicroft.plugin_skills[SKILL_ID].instance
        # keep the suite offline; routing is what we assert
        cls.skill.wiki.search = lambda *args, **kwargs: []

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _run(self, utterance, expected):
        """Emit ``utterance``, check it reached ``expected``, and return the
        matched intent message and what the skill spoke."""
        session = Session(f"e2e-{abs(hash(utterance))}")
        session.lang = LANG
        session.pipeline = PIPELINE
        capture = CaptureSession(
            self.minicroft,
            eof_msgs=["mycroft.skill.handler.complete", "ovos.intent.unmatched"])
        capture.capture(Message("recognizer_loop:utterance",
                                {"utterances": [utterance], "lang": LANG},
                                {"session": session.serialize()}), timeout=30)
        messages = capture.finish()
        TALLY.assert_routed(utterance, expected, [m.msg_type for m in messages])
        matched = next(m for m in messages
                       if canonical_intent_topic(m.msg_type) == expected)
        spoken = [m.data.get("utterance", "") for m in messages
                  if m.msg_type in ("speak", "ovos.utterance.speak")]
        return matched, spoken


class TestWikiIntentRouting(_RoutingTest):
    # The slot keeps the case the user spoke; the lookup does not depend on it.
    def test_search_wikipedia_for_topic(self):
        matched, _ = self._run("search wikipedia for tea", WIKI)
        self.assertEqual(matched.data.get("query", "").lower(), "tea")

    def test_tell_me_about_topic_on_wikipedia(self):
        matched, _ = self._run("tell me about Portugal on wikipedia", WIKI)
        self.assertEqual(matched.data.get("query", "").lower(), "portugal")

    def test_who_is_person_on_wikipedia(self):
        matched, _ = self._run("who is Albert Einstein on wikipedia", WIKI)
        self.assertEqual(matched.data.get("query", "").lower(), "albert einstein")


class TestWikiRouletteRouting(_RoutingTest):
    def test_random_wikipedia_page(self):
        self._run("play the wiki roulette", WIKIROULETTE)


class TestPronounSlotExclusion(_RoutingTest):
    def test_pure_pronoun_reprompts(self):
        """A bare pronoun must never be looked up as an article title.

        The utterance still reaches the handler, but WikipediaSkill's
        exact-match anaphora check (see ovos_skill_wikipedia/__init__.py,
        WikipediaSkill._is_anaphoric) refuses the pronoun and leaves the
        slot unresolved, so the skill re-prompts instead of searching for
        "that".
        """
        _, spoken = self._run("tell me about that on wikipedia", WIKI)
        # the intent fires, but no lookup happens for the bare pronoun
        for utterance in spoken:
            self.assertNotIn("that", utterance.lower().split(),
                             f"pronoun leaked into a Wikipedia lookup: {spoken}")
        self.assertTrue(spoken, "skill gave no response to the pronoun query")
        self.assertTrue(
            any(u.lower().startswith(("who or what", "what should"))
                for u in spoken),
            f"expected a clarification prompt, got: {spoken}",
        )

    def test_title_containing_pronoun_word_still_matches(self):
        """"the it crowd" contains the pronoun word "it" as a token, but the
        anaphora check is an exact match against the whole {query} value
        (never containment), so a real multi-word title must still resolve
        and fire the intent.
        """
        matched, _ = self._run("tell me about the it crowd on wikipedia", WIKI)
        self.assertEqual(matched.data.get("query", "").lower(), "the it crowd")
