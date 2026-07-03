"""End-to-end intent routing tests for the en-US locale.

Each canonical utterance is fired through a real MiniCroft and asserted to
route to the expected intent handler and produce a spoken response. The article
text itself depends on live search results, so assertions cover the intent
binding and the presence of a ``speak`` response, not the dialog content.
"""
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-wikipedia.openvoiceos"


class TestWikipediaIntentsEnUS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()

    def _run(self, text):
        session = Session("test-session")
        session.pipeline = [
            "ovos-adapt-pipeline-plugin-high",
            "ovos-padatious-pipeline-plugin-high",
            "ovos-adapt-pipeline-plugin-medium",
            "ovos-padatious-pipeline-plugin-medium",
            "ovos-adapt-pipeline-plugin-low",
        ]
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": [text], "lang": "en-US"},
            {"session": session.serialize(), "source": "A", "destination": "B"},
        )
        capture = CaptureSession(self.minicroft)
        capture.capture(utterance, timeout=30)
        return capture.finish()

    def _assert_intent(self, text, intent_file):
        messages = self._run(text)
        types = [m.msg_type for m in messages]
        self.assertIn(f"{SKILL_ID}:{intent_file}", types)
        self.assertTrue(any("speak" in t for t in types))

    def test_search_wikipedia_for_query(self):
        self._assert_intent("search wikipedia for the moon", "wiki.intent")

    def test_tell_me_about_query_on_wiki(self):
        self._assert_intent("tell me about the moon on wiki", "wiki.intent")

    def test_look_up_query_on_wikipedia(self):
        self._assert_intent("look up the moon on wikipedia", "wiki.intent")

    def test_what_does_wikipedia_say_about_query(self):
        self._assert_intent("what does wikipedia say about the moon", "wiki.intent")

    def test_wiki_roulette(self):
        self._assert_intent("wiki roulette", "wikiroulette.intent")

    def test_play_wikipedia_roulette(self):
        self._assert_intent("play wikipedia roulette", "wikiroulette.intent")

    def test_random_wikipedia_page(self):
        self._assert_intent("random wikipedia page", "wikiroulette.intent")


if __name__ == "__main__":
    unittest.main()
