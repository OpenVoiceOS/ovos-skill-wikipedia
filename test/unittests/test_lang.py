import json
import unittest
from unittest import skip
from unittest.mock import Mock

from ovos_utils.fakebus import FakeBus, Message
from skill_ovos_wikipedia import WikipediaSkill


class TestTranslation(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            self.bus.emitted_msgs.append(json.loads(msg))

        self.bus.on("message", get_msg)

        self.skill = WikipediaSkill()
        self.skill._startup(self.bus, "wikipedia_for_humans.test")

        self.skill.wiki.translator.translate = Mock()
        self.skill.wiki.translator.translate.return_value = "this text is in portuguese, trust me!"
        self.skill.wiki.get_expanded_answer = Mock()
        self.skill.wiki.get_expanded_answer.return_value = [
            {"title": f"title 1", "summary": f"this is the answer number 1", "img": "/tmp/wikipedia_for_humans.jpeg"},
            {"title": f"title 2", "summary": f"this is the answer number 2", "img": "/tmp/wikipedia_for_humans.jpeg"}
        ]
        self.skill.wiki.get_image = Mock()
        self.skill.wiki.get_image.return_value = "/tmp/wikipedia_for_humans.jpeg"

    @skip("Expected Message not found")
    def test_native_lang(self):
        # no translation
        self.skill.handle_search(Message("search_wikipedia_for_humans.intent",
                                         {"query": "english question here"}))
        test_messages = [{"type": msg['type'], "data": msg['data']}
                         for msg in self.bus.emitted_msgs]
        self.assertIn({'data': {'expect_response': False,
                                'lang': 'en-us',
                                'meta': {'skill': 'wikipedia_for_humans.test'},
                                'utterance': 'this is the answer number 1'},
                       'type': 'speak'}, test_messages, test_messages)

    @skip("Expected Message not found")
    def test_unk_lang(self):
        # translation
        self.skill.handle_search(Message("search_wikipedia_for_humans.intent",
                                         {"query": "not english!",
                                          "lang": "pt-pt"}))
        test_messages = [{"type": msg['type'], "data": msg['data']}
                         for msg in self.bus.emitted_msgs]
        self.assertIn(
            {'context': {'skill_id': 'wikipedia_for_humans.test'},
             'data': {'expect_response': False,
                      'lang': 'pt-pt',
                      'meta': {'skill': 'wikipedia_for_humans.test'},
                      'utterance': "this text is in portuguese, trust me!"},
             'type': 'speak'},  test_messages, test_messages)
