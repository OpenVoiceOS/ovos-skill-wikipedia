"""End-to-end intent-routing tests for the en-US Wikipedia skill.

Boots an in-process MiniCroft with the skill loaded and feeds it real
utterances through the padatious pipeline, asserting where each one routes and
how the {query} slot is filled. The network lookup is stubbed so the suite is
deterministic and offline.
"""
import time
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import get_minicroft

SKILL_ID = "ovos-skill-wikipedia.openvoiceos"
LANG = "en-US"
PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
]


def _matches_intent(msg_type: str, skill_id: str, intent_label: str) -> bool:
    """Tolerant matcher: compare the ``:``-suffix basename, extension
    stripped, so the assertion doesn't pin the wire format of any one
    pipeline plugin (same shape as the golden-utterance suite)."""
    prefix = f"{skill_id}:"
    if not msg_type.startswith(prefix):
        return False
    observed = msg_type[len(prefix):]
    observed_base = observed.rsplit(".", 1)[0] if observed.endswith(".intent") else observed
    expected_base = intent_label.rsplit(".", 1)[0] if intent_label.endswith(".intent") else intent_label
    return observed_base == expected_base


class _RoutingTest(TestCase):
    """Shared MiniCroft harness with a stubbed Wikipedia backend."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])
        cls.skill = cls.minicroft.plugin_skills[SKILL_ID].instance
        # keep the suite offline and deterministic; routing is what we assert
        cls.skill.wiki.search = lambda *args, **kwargs: []
        cls.bus = cls.minicroft.bus

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _run(self, utterance):
        """Emit ``utterance`` and collect the intent + speak messages it yields.

        Intent routing is asserted via ``_matches_intent`` (suffixed vs
        suffixless message-type normalization) rather than a hardcoded
        ``f"{SKILL_ID}:wiki.intent"`` string, so the assertion doesn't pin
        the wire format of any one pipeline plugin.
        """
        intents = []
        spoken = []

        def _on_message(m):
            if _matches_intent(m.msg_type, SKILL_ID, "wiki.intent"):
                intents.append(("wiki.intent", m.data.get("query")))
            elif _matches_intent(m.msg_type, SKILL_ID, "wikiroulette.intent"):
                intents.append(("wikiroulette.intent", None))

        # the padatious pipeline emits the message type without the
        # ".intent" suffix ("<skill_id>:wiki", not "<skill_id>:wiki.intent"),
        # so both spellings are subscribed and _matches_intent normalizes
        # whichever one actually arrives.
        for name in (f"{SKILL_ID}:wiki", f"{SKILL_ID}:wiki.intent",
                     f"{SKILL_ID}:wikiroulette", f"{SKILL_ID}:wikiroulette.intent"):
            self.bus.on(name, _on_message)
        self.bus.on("speak",
                    lambda m: spoken.append(m.data.get("utterance", "")))
        session = Session(f"e2e-{abs(hash(utterance))}")
        session.lang = LANG
        session.pipeline = PIPELINE
        self.bus.emit(Message("recognizer_loop:utterance",
                              {"utterances": [utterance], "lang": LANG},
                              {"session": session.serialize()}))
        time.sleep(3)
        return intents, spoken


class TestWikiIntentRouting(_RoutingTest):
    def test_search_wikipedia_for_topic(self):
        intents, _ = self._run("search wikipedia for tea")
        self.assertIn(("wiki.intent", "tea"), intents)

    def test_tell_me_about_topic_on_wikipedia(self):
        intents, _ = self._run("tell me about Portugal on wikipedia")
        self.assertIn(("wiki.intent", "portugal"), intents)

    def test_who_is_person_on_wikipedia(self):
        intents, _ = self._run("who is Albert Einstein on wikipedia")
        self.assertIn(("wiki.intent", "albert einstein"), intents)


class TestWikiRouletteRouting(_RoutingTest):
    def test_random_wikipedia_page(self):
        intents, _ = self._run("play the wiki roulette")
        self.assertIn(("wikiroulette.intent", None), intents)


class TestPronounSlotExclusion(_RoutingTest):
    def test_pure_pronoun_reprompts(self):
        """A bare pronoun must never be looked up as an article title.

        The utterance still reaches the handler, but WikipediaSkill's
        exact-match anaphora check (see ovos_skill_wikipedia/__init__.py,
        WikipediaSkill._is_anaphoric) refuses the pronoun and leaves the
        slot unresolved, so the skill re-prompts instead of searching for
        "that".
        """
        intents, spoken = self._run("tell me about that on wikipedia")
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
        intents, _ = self._run("tell me about the it crowd on wikipedia")
        self.assertIn(("wiki.intent", "the it crowd"), intents)
