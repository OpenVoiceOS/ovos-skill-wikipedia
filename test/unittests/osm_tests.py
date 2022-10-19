# write your first unittest!
import unittest
from os.path import exists
from shutil import rmtree

from ovos_skills_manager import SkillEntry

branch = "dev"
url = f"https://github.com/OpenVoiceOS/skill-ovos-wikipedia@{branch}"


class TestOSM(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.skill_id = "skill-ovos-wikipedia.openvoiceos"

    def test_osm_install(self):
        skill = SkillEntry.from_github_url(url)
        tmp_skills = "/tmp/osm_installed_skills"
        skill_folder = f"{tmp_skills}/{skill.uuid}"

        if exists(skill_folder):
            rmtree(skill_folder)

        updated = skill.install(folder=tmp_skills, default_branch=branch)
        self.assertEqual(updated, True)
        self.assertTrue(exists(skill_folder))

        updated = skill.install(folder=tmp_skills, default_branch=branch)
        self.assertEqual(updated, False)
