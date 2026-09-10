"""
``voc_list`` must honour the ``lang`` argument it is given instead of
always resolving vocabulary through the skill's own default language.
The skill's default is en-US; a caller asking ``voc_list`` for da-DK
vocabulary must get back da-DK strings, not the en-US ones.
"""
import unittest
from os.path import dirname

from ovos_spec_tools import expand
from ovos_utils.messagebus import FakeBus

import ovos_skill_wikipedia
from ovos_skill_wikipedia import WikipediaSkill

DA_PRONOUNS = {
    "de", "dem", "den", "denne", "dens", "deres", "det", "dets", "dette",
    "disse", "ham", "han", "hans", "hende", "hendes", "hun",
}
EN_PRONOUNS = {
    "he", "she", "it", "they", "him", "her", "them", "his", "hers", "its",
    "their", "theirs", "that", "this", "those", "these",
}


class TestVocListLang(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.skill_id = "ovos-skill-wikipedia.openvoiceos"
        cls.root_dir = dirname(ovos_skill_wikipedia.__file__)

    def setUp(self):
        self.bus = FakeBus()
        self.skill = WikipediaSkill()
        self.skill._startup(self.bus, self.skill_id)
        self.addCleanup(self.skill.default_shutdown)

    def test_voc_list_returns_requested_lang_vocab(self):
        self.assertEqual(self.skill.lang, "en-US")

        da_lines = self.skill.voc_list("pronoun", lang="da-DK")
        da_samples = set()
        for line in da_lines:
            da_samples.update(expand(line))
        self.assertEqual(da_samples, DA_PRONOUNS)
        self.assertTrue(da_samples.isdisjoint(EN_PRONOUNS))

    def test_is_anaphoric_uses_requested_lang(self):
        self.assertTrue(self.skill._is_anaphoric("han", "da-DK"))
        self.assertFalse(self.skill._is_anaphoric("python", "da-DK"))


if __name__ == "__main__":
    unittest.main()
