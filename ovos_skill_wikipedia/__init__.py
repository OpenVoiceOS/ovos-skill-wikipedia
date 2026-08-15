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
from typing import Optional, Tuple

import requests
from ovos_bus_client.session import SessionManager
from ovos_utils import classproperty
from ovos_utils.process_utils import RuntimeRequirements
from ovos_wikipedia import WikipediaRetrievalEngine, WikipediaResult
from ovos_workshop.decorators import intent_handler, common_query
from ovos_workshop.skills.ovos import OVOSSkill


class WikipediaSkill(OVOSSkill):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_results = {}
        self.wiki = WikipediaRetrievalEngine(self.settings)

    @classproperty
    def runtime_requirements(self):
        """ indicate to OVOS this skill should ONLY
         be loaded if we have internet connection"""
        return RuntimeRequirements(
            internet_before_load=True,
            network_before_load=True,
            gui_before_load=False,
            requires_internet=True,
            requires_network=True,
            requires_gui=False,
            no_internet_fallback=False,
            no_network_fallback=False,
            no_gui_fallback=True,
        )

    def _is_anaphoric(self, phrase: str, lang: str) -> bool:
        """True if ``phrase`` is *exactly* an anaphoric pronoun (no partial
        containment): "the it crowd" or "her majesty" are real article
        titles and must never be rejected just because they contain a
        pronoun word.
        """
        return phrase.strip().lower() in set(self.voc_list("pronoun", lang=lang))

    # explicit wikipedia requests
    @intent_handler("wiki.intent", voc_blacklist=["weather"])
    def handle_search(self, message):
        """Extract what the user asked about and reply with info
        from wikipedia.
        """
        query = message.data.get("query", "")
        sess = SessionManager.get()
        if not query.strip() or self._is_anaphoric(query, sess.lang):
            # bare pronoun / unresolved slot: leave the lookup to a later
            # stage (context fill or a re-prompt) instead of searching for it
            self.speak_dialog("no_query")
            return
        if sess.session_id == "default":
            self.gui.show_animated_image("jumping.gif")
        self.speak_dialog("searching", {"query": query})
        results = self.wiki.search(query, lang=sess.lang)
        if results:
            best = results[0]
            self.speak(best.best_passage or best.summary)
        else:
            self.speak_dialog("no_answer")

    def _get_random_page(self, lang: str) -> Optional[WikipediaResult]:
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {"action": "query", "list": "random", "rnnamespace": 0, "rnlimit": 1, "format": "json"}
        try:
            resp = requests.get(url, params=params, timeout=10, headers={"User-Agent": self.wiki.USER_AGENT})
            resp.raise_for_status()
            page = resp.json()["query"]["random"][0]
            return self.wiki._get_page_data(str(page["id"]), lang)
        except Exception:
            return None

    @intent_handler("wikiroulette.intent")
    def handle_wiki_roulette_query(self, message):
        """Speak a random Wikipedia page."""
        sess = SessionManager.get()
        lang = sess.lang.split("-")[0]
        if sess.session_id == "default":
            self.gui.show_animated_image("jumping.gif")
        self.speak_dialog("wikiroulette")
        result = self._get_random_page(lang)
        if result:
            self.speak(result.title + ". " + (result.best_passage or result.summary))
            if sess.session_id == "default" and result.image:
                self.gui.show_image(result.image)
        else:
            self.speak_dialog("no_answer")

    # common query
    def cq_callback(self, utterance: str, answer: str, lang: str):
        """ If selected show gui """
        sess = SessionManager.get()
        img = self.session_results.get(sess.session_id, {}).get("image")
        if img:
            self.gui.show_image(img)

    @common_query(callback=cq_callback)
    def match_common_query(self, phrase: str, lang: str) -> Tuple[str, float]:

        last_word = phrase.strip().split()[-1] if phrase.strip() else ""
        if (self.voc_match(phrase, "misc_blacklist") or
                self.voc_match(phrase, "weather") or
                self._is_anaphoric(last_word, lang)):
            # bare anaphora ("who is he", "what about it") has no article to
            # look up; decline rather than searching wikipedia for the
            # pronoun itself. checked against the trailing word only, an
            # exact match rather than containment, so real titles that merely
            # end in a non-pronoun word ("her majesty", "the it crowd") are
            # still searched
            return None

        sess = SessionManager.get()
        self.session_results[sess.session_id] = {
            "query": phrase,
            "results": [],
            "lang": lang,
            "image": None
        }
        results = self.wiki.search(phrase, lang=sess.lang)
        if results:
            best = results[0]
            self.log.info(f"Wikipedia answer: {best.summary}")
            self.session_results[sess.session_id]["results"] = results
            self.session_results[sess.session_id]["image"] = best.image
            return best.summary, best.conf
