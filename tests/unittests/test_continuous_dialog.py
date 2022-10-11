import json
import unittest
from time import sleep
from unittest.mock import Mock

from ovos_utils.messagebus import FakeBus, Message
from skill_ovos_wikipedia import WikipediaSkill


class TestDialog(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            self.bus.emitted_msgs.append(json.loads(msg))

        self.bus.on("message", get_msg)

        self.skill = WikipediaSkill()
        self.skill._startup(self.bus, "wikipedia_for_humans.test")
        self.skill.wiki.get_expanded_answer = Mock()
        self.skill.wiki.get_expanded_answer.return_value = [
            {"title": f"title 1", "summary": f"this is the answer number 1", "img": "/tmp/wikipedia_for_humans.jpeg"},
            {"title": f"title 2", "summary": f"this is the answer number 2", "img": "/tmp/wikipedia_for_humans.jpeg"}
        ]
        self.skill.wiki.get_image = Mock()
        self.skill.wiki.get_image.return_value = "/tmp/wikipedia_for_humans.jpeg"
        self.skill.has_context = False

        def set_context(message):
            self.skill.has_context = True

        def unset_context(message):
            self.skill.has_context = False

        self.bus.on('add_context', set_context)
        self.bus.on('remove_context', unset_context)

    def test_continuous_dialog(self):
        self.bus.emitted_msgs = []

        # "ask the wiki X"
        self.assertFalse(self.skill.has_context)
        self.skill.handle_search(Message("search_wikipedia_for_humans.intent",
                                         {"query": "what is the speed of light"}))

        print(self.bus.emitted_msgs)
        self.assertIn({'context': {'skill_id': 'wikipedia_for_humans.test'},
                       'data': {'context': 'wikipedia_for_humans_testWikiKnows',
                                'origin': '',
                                'word': 'what is the speed of light'},
                       'type': 'add_context'}, self.bus.emitted_msgs)
        self.assertIn(
            {'context': {'skill_id': 'wikipedia_for_humans.test'},
             'data': {'expect_response': False,
                      'lang': 'en-us',
                      'meta': {'skill': 'wikipedia_for_humans.test'},
                      'utterance': 'this is the answer number 1'},
             'type': 'speak'}, self.bus.emitted_msgs)

        # "tell me more"
        self.assertTrue(self.skill.has_context)
        self.skill.handle_tell_more(Message("WikiMore"))

        self.assertIn(
            {'context': {'skill_id': 'wikipedia_for_humans.test'},
             'data': {'expect_response': False,
                      'lang': 'en-us',
                      'meta': {'skill': 'wikipedia_for_humans.test'},
                      'utterance': 'this is the answer number 2'},
             'type': 'speak'}, self.bus.emitted_msgs)
        self.assertTrue(self.skill.has_context)

        # "tell me more" - no more data dialog
        self.skill.handle_tell_more(Message("WikiMore"))
        sleep(0.5)
        self.assertEqual(self.bus.emitted_msgs[-2]["type"], "speak")
        self.assertEqual(self.bus.emitted_msgs[-2]["data"]["meta"],
                         {'data': {}, 'dialog': 'thats all', 'skill': 'wikipedia_for_humans.test'})

        # removal of context to disable "tell me more"
        self.assertIn(
            {'context': {'skill_id': 'wikipedia_for_humans.test'},
             'data': {'context': 'wikipedia_for_humans_testWikiKnows'},
             'type': 'remove_context'}, self.bus.emitted_msgs)
        self.assertFalse(self.skill.has_context)
