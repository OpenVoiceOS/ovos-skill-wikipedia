import json
import unittest
from unittest.mock import Mock

from ovos_workshop.skills.fallback import FallbackSkill
from ovos_skill_common_query import QuestionsAnswersSkill
from ovos_utils.messagebus import FakeBus, Message
from skill_ovos_wikipedia import WikipediaSkill


class TestCommonQuery(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            self.bus.emitted_msgs.append(json.loads(msg))

        self.bus.on("message", get_msg)

        self.skill = WikipediaSkill()
        self.skill._startup(self.bus, "wikipedia_for_humans.test")
        self.skill.wiki.long_answer = Mock()
        self.skill.wiki.long_answer.return_value = [
            {"title": "wikipedia_for_humans skill", "summary": "the answer is always 42"}
        ]
        self.skill.wiki.get_image = Mock()
        self.skill.wiki.get_image.return_value = "/wikipedia_for_humans.jpeg"
        self.bus.emitted_msgs = []

        self.cc = QuestionsAnswersSkill()
        self.cc._startup(self.bus, "common_query.test")

    def test_skill_id(self):
        self.assertEqual(self.cc.skill_id, "common_query.test")

        # if running in ovos-core every message will have the skill_id in context
        for msg in self.bus.emitted_msgs:
            self.assertEqual(msg["context"]["skill_id"], "common_query.test")

    def test_intent_register(self):
        # helper .voc files only, no intents
        self.assertTrue(isinstance(self.cc, FallbackSkill))

        adapt_ents = ["common_query_testQuestion"]
        for msg in self.bus.emitted_msgs:
            if msg["type"] == "register_vocab":
                self.assertTrue(msg["data"]["entity_type"] in adapt_ents)

    def test_registered_events(self):
        registered_events = [e[0] for e in self.cc.events]

        # common query event handlers
        common_query = ['question:query.response']
        for event in common_query:
            self.assertTrue(event in registered_events)

        # base skill class events shared with mycroft-core
        default_skill = ["mycroft.skill.enable_intent",
                         "mycroft.skill.disable_intent",
                         "mycroft.skill.set_cross_context",
                         "mycroft.skill.remove_cross_context",
                         "intent.service.skills.deactivated",
                         "intent.service.skills.activated",
                         "mycroft.skills.settings.changed"]
        for event in default_skill:
            self.assertTrue(event in registered_events)

        # base skill class events exclusive to ovos-core
        default_ovos = ["skill.converse.ping",
                        "skill.converse.request",
                        f"{self.cc.skill_id}.activate",
                        f"{self.cc.skill_id}.deactivate"]
        for event in default_ovos:
            self.assertTrue(event in registered_events)

    def test_common_query_events(self):
        self.bus.emitted_msgs = []
        self.cc.handle_question(Message("fallback_cycle_test",
                                        {"utterance": "what is the speed of light"}))

        expected = [
            # thinking animation
            {'type': 'enclosure.mouth.think',
             'data': {},
             'context': {'destination': ['enclosure'],
                         'skill_id': 'common_query.test'}},
            # send query
            {'type': 'question:query',
             'data': {'phrase': 'what is the speed of light'},
             'context': {'skill_id': 'common_query.test'}},

            # skill announces its searching
            {'type': 'question:query.response',
             'data': {'phrase': 'what is the speed of light',
                      'skill_id': 'wikipedia_for_humans.test',
                      'searching': True},
             'context': {'skill_id': 'wikipedia_for_humans.test'}},

            # skill context set by skill for continuous dialog
            {'type': 'add_context',
             'data': {'context': 'wikipedia_for_humans_testWikiKnows',
                      'word': 'what is the speed of light',
                      'origin': ''},
             'context': {'skill_id': 'wikipedia_for_humans.test'}},

            # final wikipedia_for_humans response
            {'type': 'question:query.response',
             'data': {'phrase': 'what is the speed of light',
                      'skill_id': 'wikipedia_for_humans.test',
                      'answer': "the answer is always 42",
                      'callback_data': {'query': 'what is the speed of light',
                                        'image': "/wikipedia_for_humans.jpeg",
                                        'answer': "the answer is always 42"},
                      'conf': 0.0},
             'context': {'skill_id': 'wikipedia_for_humans.test'}},

            # stop thinking animation
            {'type': 'enclosure.mouth.reset',
             'data': {},
             'context': {'destination': ['enclosure'],
                         'skill_id': 'common_query.test'}
             },

            # tell enclosure about active skill (speak method)
            {'type': 'enclosure.active_skill',
             'data': {'skill_id': 'common_query.test'},
             'context': {'destination': ['enclosure'],
                         'skill_id': 'common_query.test'}},

            # execution of speak method
            {'type': 'speak',
             'data': {'utterance': 'the answer is always 42',
                      'expect_response': False,
                      'meta': {'skill': 'common_query.test'},
                      'lang': 'en-us'},
             'context': {'skill_id': 'common_query.test'}},

            # skill callback event
            {'type': 'question:action',
             'data': {'skill_id': 'wikipedia_for_humans.test',
                      'phrase': 'what is the speed of light',
                      'callback_data': {'query': 'what is the speed of light',
                                        'image': '/wikipedia_for_humans.jpeg',
                                        'answer': 'the answer is always 42'}},
             'context': {'skill_id': 'common_query.test'}},

            # theres a couple more gui protocol messages after
            # optional and irrelevant for these tests
        ]

        for ctr, msg in enumerate(expected):
            # ignore conf value, we are not testing that
            m = self.bus.emitted_msgs[ctr]
            if m["data"].get("conf"):
                m["data"]["conf"] = 0.0
            self.assertEqual(msg, m)

    @unittest.skip("TODO - debug and fix me")
    def test_common_query_events_routing(self):
        # common query message life cycle
        self.bus.emitted_msgs = []
        self.cc.handle_question(Message("fallback_cycle_test",
                                        {"utterance": "what is the speed of light"},
                                        {"source": "unittests",
                                         "destination": "common_query"}))

        # "source" should receive these
        unittest_msgs = set([m["type"] for m in self.bus.emitted_msgs
                             if m["context"].get("destination", "") == "unittests"])
        self.assertEqual(unittest_msgs, {'question:query',
                                         'question:query.response',
                                         'question:action',
                                         'add_context',
                                         'speak'})

        # internal to mycroft, "source" should NOT receive these
        # TODO fix bug - these messages should not be dropping context
        # these should in fact also be sent ...
        cc_msgs = set([m["type"] for m in self.bus.emitted_msgs
                       if m["context"].get("destination", "") != "unittests"])
        for m in cc_msgs:
            self.assertTrue(m.startswith("enclosure.") or
                            m.startswith("gui."))
