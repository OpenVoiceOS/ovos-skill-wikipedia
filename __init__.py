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
from os.path import join, dirname

import wikipedia_for_humans
from adapt.intent import IntentBuilder
from mycroft.skills.common_query_skill import CommonQuerySkill, CQSMatchLevel
from mycroft.skills.core import intent_handler
from neon_solver_wikipedia_plugin import WikipediaSolver
from quebra_frases import sentence_tokenize
from requests.exceptions import ConnectionError


class WikipediaSkill(CommonQuerySkill):
    def __init__(self):
        super(WikipediaSkill, self).__init__(name="WikipediaSkill")
        self.wiki = WikipediaSolver()
        self.idx = 0
        self.results = []
        self.current_picture = None
        self.current_title = None

    # intents
    @intent_handler("wiki.intent")
    def handle_wiki_query(self, message):
        """ Extract what the user asked about and reply with info
            from wikipedia.
        """
        self.gui.show_animated_image(join(dirname(__file__), "ui",
                                          "jumping.gif"))
        search = message.data.get("query")
        self.current_picture = None
        self.current_title = search
        self.speak_dialog("searching", {"query": search})
        self.search_and_speak(search)

    @intent_handler("wikiroulette.intent")
    def handle_wiki_roulette_query(self, message):
        """ Random wikipedia page """
        self.gui.show_animated_image(join(dirname(__file__), "ui",
                                          "jumping.gif"))
        self.current_picture = None
        self.current_title = "Wiki Roulette"
        self.speak_dialog("wikiroulette")
        self.search_and_speak()

    @intent_handler(IntentBuilder("WikiMore").require("More").
                    require("wiki_article"))
    def handle_tell_more(self, message):
        """ Follow up query handler, "tell me more".

            If a "spoken_lines" entry exists in the active contexts
            this can be triggered.
        """
        self.speak_next_result()

    # common query
    def CQS_match_query_phrase(self, utt):
        data = self.extract_and_search(utt)
        summary = data["summary"]
        if summary:
            self.current_picture = data.get("images") or []
            self.current_title = data.get("title") or utt
            self.results = sentence_tokenize(summary)
            return (utt, CQSMatchLevel.GENERAL, self.results[0],
                    {'query': utt,
                     'answer': self.results[0]})

    def CQS_action(self, phrase, data):
        """ If selected show gui """
        self.display_wiki_entry()
        self.set_context("wiki_article", data["title"])

    # wikipedia
    def extract_and_search(self, search=None):
        if "lang" in self.settings:
            lang = self.settings["lang"]
        else:
            lang = self.lang.split("-")[0]
        try:
            if search:
                return self.wiki.extract_and_search(search, context={"lang": lang})
            else:
                return wikipedia_for_humans.wikiroulette(lang=lang)
        except ConnectionError as e:
            self.log.error("It seems like lang is invalid!!!")
            self.log.error(lang + ".wikipedia.org does not seem to exist")
            self.log.info("Override 'lang' in skill settings")
            # TODO dialog
            # TODO Settings meta
            raise e  # just speak regular skill error

    def search_and_speak(self, search=None):
        data = self.extract_and_search(search)
        self._speak_wiki(data)

    def speak_next_result(self):
        if self.idx + 1 > len(self.results):
            self.speak_dialog("thats all")
            self.remove_context("wiki_article")
            self.idx = 0
        else:
            self.speak(self.results[self.idx])
            self.idx += 1
        self.set_context("Wikipedia", "wikipedia")
        self.display_wiki_entry()

    def _speak_wiki(self, data):
        self.current_picture = data["images"]
        self.current_title = data["title"]
        answer = data["summary"]
        if not answer.strip():
            self.gui.clear()
            self.speak_dialog("no entry found")
            return
        self.idx = 0
        self.results = sentence_tokenize(answer)
        self.speak_next_result()
        self.set_context("wiki_article", data["title"])

    def display_wiki_entry(self):
        if self.current_picture and len(self.current_picture):
            self.gui.show_image(self.current_picture[0],
                                title=self.current_title, fill=None,
                                override_idle=20, override_animations=True)

    def stop(self):
        self.gui.release()


def create_skill():
    return WikipediaSkill()
