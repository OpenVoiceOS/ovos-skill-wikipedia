from ovos_skills_manager import SkillEntry
from os.path import exists, join, dirname
from shutil import rmtree
import os
from os import makedirs
import json
from ovos_utils.bracket_expansion import expand_parentheses, expand_options


branch = "dev"
repo = "skill-ovos-wikipedia"
author = "OpenVoiceOS"

url = f"https://github.com/{author}/{repo}@{branch}"

skill = SkillEntry.from_github_url(url)
tmp_skills = "/tmp/osm_installed_skills"
skill_folder = f"{tmp_skills}/{skill.uuid}"

base_dir = dirname(dirname(__file__))
desktop_dir = join(base_dir, "res", "desktop")
android_ui = join(base_dir, "ui", "+android")
makedirs(desktop_dir, exist_ok=True)

readme = join(base_dir, "README.md")
jsonf = join(desktop_dir, "skill.json")
desktopf = join(desktop_dir, f"{repo}.desktop")
skill_code = join(base_dir, "__init__.py")

res_folder = join(base_dir, "locale", "en-us")


def read_samples(path):
    samples = []
    with open(path) as fi:
        for _ in fi.read().split("\n"):
            if _ and not _.strip().startswith("#"):
                samples += expand_options(_)
    return samples

samples = []
for root, folders, files in os.walk(res_folder):
    for f in files:
        if f.endswith(".intent"):
            samples += read_samples(join(root, f))
skill._data["examples"] = list(set(samples))

has_android = exists(android_ui)
with open(skill_code) as f:
    has_homescreen = f"{repo}.{author}.home" in f.read()

if not exists(readme):
    with open(readme, "w") as f:
        f.write(skill.generate_readme())

if has_homescreen and not exists(desktopf):
    with open(desktopf, "w") as f:
        f.write(skill.desktop_file)

if not exists(jsonf):
    data = skill.json
    with open(jsonf, "w") as f:
        if not has_android or not has_homescreen:
            data.pop("android")
        if not has_homescreen:
            data.pop("desktop")
            data["desktopFile"] = False
else:
    with open(jsonf) as f:
        data = json.load(f)

# set dev branch
data["branch"] = "dev"

with open(jsonf, "w") as f:
    json.dump(data, f, indent=4)
