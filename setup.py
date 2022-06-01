#!/usr/bin/env python3
from setuptools import setup

# skill_id=package_name:SkillClass
PLUGIN_ENTRY_POINT = 'skill-wikipedia-for-humans.jarbasai=skill_wikipedia_for_humans:WikipediaSkill'

setup(
    # this is the package name that goes on pip
    name='skill-wikipedia-for-humans',
    version='0.0.1',
    description='mycroft/ovos wikipedia skill plugin',
    url='https://github.com/JarbasSkills/skill-wikipedia-for-humans',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    package_dir={"skill_wikipedia_for_humans": ""},
    package_data={'skill_wikipedia_for_humans': ['locale/*', 'vocab/*', "dialog/*"]},
    packages=['skill_wikipedia_for_humans'],
    include_package_data=True,
    install_requires=["wikipedia_for_humans~=0.2.3"],
    keywords='ovos skill plugin',
    entry_points={'ovos.plugin.skill': PLUGIN_ENTRY_POINT}
)
