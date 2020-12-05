# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import wikipedia_for_humans
from requests.exceptions import ConnectionError
from adapt.intent import IntentBuilder
from mycroft.skills.core import (MycroftSkill, intent_handler,
                                 intent_file_handler)
from mycroft.messagebus.message import Message
from mycroft.configuration import LocalConf, USER_CONFIG,Configuration


class WikipediaSkill(MycroftSkill):
    def __init__(self):
        super(WikipediaSkill, self).__init__(name="WikipediaSkill")
        self.idx = 0
        self.results = []

    def initialize(self):
        self.blacklist_default_skill()

    def blacklist_default_skill(self):
        core_conf = Configuration.load_config_stack()
        blacklist = core_conf["skills"]["blacklisted_skills"]
        if "mycroft-wiki.mycroftai" not in blacklist:
            self.log.debug("Blacklisting official mycroft wikipedia skill")
            blacklist.append("mycroft-wiki.mycroftai")
            conf = LocalConf(USER_CONFIG)
            if "skills" not in conf:
                conf["skills"] = {}
            conf["skills"]["blacklisted_skills"] = blacklist
            conf.store()

        self.bus.emit(Message("detach_skill",
                              {"skill_id": "mycroft-wiki.mycroftai"}))

    def speak_result(self):
        if self.idx + 1 > len(self.results):
            self.speak_dialog("thats all")
            self.remove_context("wiki_article")
            self.idx = 0
        else:
            self.speak(self.results[self.idx])
            self.idx += 1
        self.set_context("Wikipedia", "wikipedia")

    @intent_handler(IntentBuilder("WikiSearch").require("Wikipedia").
                    require("ArticleTitle"))
    def handle_wiki_query(self, message):
        """ Extract what the user asked about and reply with info
            from wikipedia.
        """
        # Talk to the user, as this can take a little time...
        search = message.data.get("ArticleTitle")
        self.speak_dialog("searching", {"query": search})
        if "lang" in self.settings:
            lang = self.settings["lang"]
        else:
            lang = self.lang.split("-")[0]
        try:
            answer = wikipedia_for_humans.summary(search, lang=lang)
            if not answer.strip():
                self.speak_dialog("no entry found")
                return
            self.log.debug("Wiki summary: " + answer)
            self.idx = 0
            self.results = answer.split(". ")
            self.speak_result()
            self.set_context("wiki_article", search)
        except ConnectionError as e:
            self.log.error("It seems like lang is invalid!!!")
            self.log.error(lang + ".wikipedia.org does not seem to exist")
            self.log.info("Override this in skill settings")
            # TODO dialog
            # TODO Settings meta
            raise e  # just speak regular error

    @intent_handler(IntentBuilder("WikiMore").require("More").
                    require("wiki_article"))
    def handle_tell_more(self, message):
        """ Follow up query handler, "tell me more".

            If a "spoken_lines" entry exists in the active contexts
            this can be triggered.
        """
        self.speak_result()


def create_skill():
    return WikipediaSkill()
