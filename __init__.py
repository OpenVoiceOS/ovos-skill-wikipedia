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
from ovos_utils.skills import blacklist_skill


class WikipediaSkill(MycroftSkill):
    def __init__(self):
        super(WikipediaSkill, self).__init__(name="WikipediaSkill")
        self.idx = 0
        self.results = []
        self.current_picture = None
        self.current_title = None

    def initialize(self):
        blacklist_skill("mycroft-wiki.mycroftai")

    def display_wiki_entry(self):
        if self.current_picture and len(self.current_picture):
            self.gui.show_image(self.current_picture[0],
                                title=self.current_title, fill=None,
                                override_idle=20, override_animations=True)

    def speak_result(self):
        if self.idx + 1 > len(self.results):
            self.speak_dialog("thats all")
            self.remove_context("wiki_article")
            self.idx = 0
        else:
            self.speak(self.results[self.idx])
            self.idx += 1
        self.set_context("Wikipedia", "wikipedia")
        self.display_wiki_entry()

    @intent_handler("wiki.intent")
    def handle_wiki_query(self, message):
        """ Extract what the user asked about and reply with info
            from wikipedia.
        """
        search = message.data.get("query")
        self.current_picture = None
        self.current_title = search
        self.speak_dialog("searching", {"query": search})
        if "lang" in self.settings:
            lang = self.settings["lang"]
        else:
            lang = self.lang.split("-")[0]
        try:
            data = wikipedia_for_humans.page_data(search, lang=lang)
            self._speak_wiki(data)
        except ConnectionError as e:
            self.log.error("It seems like lang is invalid!!!")
            self.log.error(lang + ".wikipedia.org does not seem to exist")
            self.log.info("Override 'lang' in skill settings")
            # TODO dialog
            # TODO Settings meta
            raise e  # just speak regular skill error

    @intent_handler("wikiroulette.intent")
    def handle_wiki_roulette_query(self, message):
        """ Random wikipedia page """
        self.current_picture = None
        self.current_title = "Wiki Roulette"
        # TODO GUI animation
        self.speak_dialog("wikiroulette")
        if "lang" in self.settings:
            lang = self.settings["lang"]
        else:
            lang = self.lang.split("-")[0]
        try:
            data = wikipedia_for_humans.wikiroulette(lang=lang)
            self._speak_wiki(data)
        except ConnectionError as e:
            self.log.error("It seems like lang is invalid!!!")
            self.log.error(lang + ".wikipedia.org does not seem to exist")
            self.log.info("Override 'lang' in skill settings")
            # TODO dialog
            # TODO Settings meta
            raise e  # just speak regular skill error

    def _speak_wiki(self, data):
        self.current_picture = data["images"]
        self.current_title = data["title"]
        answer = data["summary"]
        if not answer.strip():
            self.speak_dialog("no entry found")
            return
        self.log.debug("Wiki summary: " + answer)
        self.idx = 0
        self.results = answer.split(". ")
        self.speak_result()
        self.set_context("wiki_article", search)

    @intent_handler(IntentBuilder("WikiMore").require("More").
                    require("wiki_article"))
    def handle_tell_more(self, message):
        """ Follow up query handler, "tell me more".

            If a "spoken_lines" entry exists in the active contexts
            this can be triggered.
        """
        self.speak_result()

    def stop(self):
        self.gui.release()


def create_skill():
    return WikipediaSkill()


