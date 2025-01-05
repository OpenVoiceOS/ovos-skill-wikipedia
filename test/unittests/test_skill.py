import json
import unittest

import requests
from ovos_utils.fakebus import FakeBus
from skill_ovos_wikipedia import WikipediaSkill
from ovos_workshop.skills.common_query_skill import CommonQuerySkill


class TestSkill(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.bus.emitted_msgs = []

        def get_msg(msg):
            self.bus.emitted_msgs.append(json.loads(msg))

        self.bus.on("message", get_msg)

        self.skill = WikipediaSkill()
        self.skill._startup(self.bus, "wikipedia_for_humans.test")

    def test_skill_id(self):
        self.assertEqual(self.skill.skill_id, "wikipedia_for_humans.test")
        # if running in ovos-core every message will have the skill_id in context
        for msg in self.bus.emitted_msgs:
            if msg["type"] != "gui.volunteer_page_upload":
                self.assertEqual(msg["context"].get("skill_id"),
                                 "wikipedia_for_humans.test", msg)

    def test_intent_register(self):
        adapt_ents = ["wikipedia_for_humans_testMore"]  # why are you different :(
        adapt_intents = ["wikipedia_for_humans.test:WikiMore"]
        padatious_intents = ["wikipedia_for_humans.test:wiki.intent",
                             # "wikipedia_for_humans.test:wikiroulette.intent"
                             ]
        for msg in self.bus.emitted_msgs:
            if msg["type"] == "register_vocab":
                self.assertTrue(msg["data"]["entity_type"] in adapt_ents)
            elif msg["type"] == "register_intent":
                self.assertTrue(msg["data"]["name"] in adapt_intents)
            elif msg["type"] == "padatious:register_intent":
                self.assertTrue(msg["data"]["name"] in padatious_intents)

    def test_registered_events(self):
        registered_events = [e[0] for e in self.skill.events]

        # common query event handlers
        self.assertTrue(isinstance(self.skill, CommonQuerySkill))
        common_query = ['question:action',
                        'question:query']
        for event in common_query:
            self.assertTrue(event in registered_events)

        # intent events
        intent_triggers = [f"{self.skill.skill_id}:WikiMore",
                           f"{self.skill.skill_id}:wiki.intent",
                          # f"{self.skill.skill_id}:wikiroulette.intent"
                           ]
        for event in intent_triggers:
            print(event)
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
                        f"{self.skill.skill_id}.activate",
                        f"{self.skill.skill_id}.deactivate"]
        for event in default_ovos:
            self.assertTrue(event in registered_events)

    def test_solver_get_data(self):
        solver = self.skill.wiki
        test_queries = ("rocks", "paper", "scissors", "computers")
        for query in test_queries:
            data = solver.get_data(query)
            self.assertIsInstance(data["title"], str)
            self.assertIsInstance(data["short_answer"], str)
            self.assertIsInstance(data["summary"], str)
            self.assertIsInstance(data["img"], str)
            image = requests.get(data["img"],
                                 headers={"User-Agent": "ovos-skill-unit-test"})
            self.assertTrue(image.ok, image)
