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

from ovos_utils.gui import can_use_gui
import wikipedia_for_humans
from adapt.intent import IntentBuilder
from mycroft.skills.common_query_skill import CommonQuerySkill, CQSMatchLevel
from mycroft.skills.core import intent_handler
from neon_solver_wikipedia_plugin import WikipediaSolver
from quebra_frases import sentence_tokenize
from requests.exceptions import ConnectionError
from ovos_utils.process_utils import RuntimeRequirements
from ovos_utils import classproperty


class WikipediaSkill(CommonQuerySkill):
    def __init__(self):
        super(WikipediaSkill, self).__init__(name="WikipediaSkill")

    def initialize(self):
        if "lang" in self.settings:
            lang = self.settings["lang"]
        else:
            lang = self.lang.split("-")[0]

        self.wiki = WikipediaSolver(config={"lang": lang})

        # for usage in tell me more / follow up questions
        self.idx = 0
        self.results = []
        self.image = None

    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(internet_before_load=True,
                                   network_before_load=True,
                                   gui_before_load=False,
                                   requires_internet=True,
                                   requires_network=True,
                                   requires_gui=False,
                                   no_internet_fallback=False,
                                   no_network_fallback=False,
                                   no_gui_fallback=True)

    # intents
    @intent_handler("wiki.intent")
    def handle_search(self, message):
        """ Extract what the user asked about and reply with info
            from wikipedia.
        """
        self.gui.show_animated_image(join(dirname(__file__), "ui",
                                          "jumping.gif"))
        self.current_title = query = message.data["query"]
        self.speak_dialog("searching", {"query": query})
        self.image = None
        summary = self.ask_the_wiki(query)
        if summary:
            self.speak_result()
        else:
            self.speak_dialog("no_answer")

    # @intent_handler("wikiroulette.intent")
    def handle_wiki_roulette_query(self, message):
        """ Random wikipedia page """
        self.gui.show_animated_image(join(dirname(__file__), "ui",
                                          "jumping.gif"))
        self.image = None
        self.current_title = "Wiki Roulette"
        self.speak_dialog("wikiroulette")
        # TODO

    @intent_handler(IntentBuilder("WikiMore").require("More").
                    require("wiki_article"))
    def handle_tell_more(self, message):
        """ Follow up query handler, "tell me more".

            If a "spoken_lines" entry exists in the active contexts
            this can be triggered.
        """
        self.speak_result()

    # common query
    def CQS_match_query_phrase(self, utt):
        summary = self.ask_the_wiki(utt)
        if summary:
            self.idx += 1  # spoken by common query
            return (utt, CQSMatchLevel.GENERAL, summary,
                    {'query': utt,
                     'image': self.image,
                     'answer': summary})

    def CQS_action(self, phrase, data):
        """ If selected show gui """
        self.display_wiki_entry()
        self.set_context("WikiKnows", data["title"])

    # wikipedia
    def ask_the_wiki(self, query):
        # context for follow up questions
        self.set_context("WikiKnows", query)
        self.idx = 0
        self.results = self.wiki.long_answer(query, lang=self.lang)
        self.image = self.wiki.get_image(query)
        if self.results:
            return self.results[0]["summary"]

    def display_wiki_entry(self, title="Wikipedia", image=None):
        if not can_use_gui(self.bus):
            return
        image = image or self.image
        if image:
            self.gui.show_image(image,
                                title=title, fill=None,
                                override_idle=20, override_animations=True)

    def speak_result(self):
        if self.idx + 1 > len(self.results):
            self.speak_dialog("thats all")
            self.remove_context("WikiKnows")
            self.idx = 0
        else:
            self.speak(self.results[self.idx]["summary"])
            self.set_context("WikiKnows", "wikipedia")
            self.display_wiki_entry(self.results[self.idx].get("title", "Wikipedia"))
            self.idx += 1

    def stop(self):
        self.gui.release()


def create_skill():
    return WikipediaSkill()
