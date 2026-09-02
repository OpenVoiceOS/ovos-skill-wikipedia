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
import re
from typing import List, Optional, Tuple

import requests
from ovos_bus_client.session import SessionManager
from ovos_spec_tools.context import resolve_key
from ovos_utils import classproperty
from ovos_utils.process_utils import RuntimeRequirements
from ovos_wikipedia import WikipediaRetrievalEngine, WikipediaResult
from ovos_workshop.decorators import intent_handler, common_query
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.ovos import OVOSSkill

# `self.set_context`/`remove_context` only accept string values (adapt-engine
# legacy context words), so title + remaining chunks are packed into one
# string on this separator rather than a dict, and split back apart on read.
_CONTEXT_SEP = "\x1f"


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

    @staticmethod
    def _remaining_chunks(summary: str, spoken: str) -> List[str]:
        """Split whatever of ``summary`` was not already ``spoken`` into
        sentence-sized chunks, for a follow-up "tell me more" to work
        through one at a time.

        ``spoken`` is either the full summary (nothing left) or a shorter
        QA-selected passage drawn from within it (the rest of the summary
        is still unread).
        """
        text = summary or ""
        if spoken and spoken == text:
            text = ""
        elif spoken and spoken in text:
            text = text.replace(spoken, "", 1)
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

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
            spoken = best.best_passage or best.summary
            self.speak(spoken)
            chunks = self._remaining_chunks(best.summary, spoken)
            if chunks:
                self.set_context("prev_wiki_article",
                                  _CONTEXT_SEP.join([best.title] + chunks),
                                  origin="wiki.intent")
        else:
            self.speak_dialog("no_answer")

    def _read_prev_wiki_article(self, message) -> Tuple[str, List[str]]:
        """Read the "prev_wiki_article" adapt-engine context back out of the
        session (`self.set_context` writes it private-scoped, owned by this
        skill -- `message.data` doesn't reliably carry the stored value
        back, per OVOS-CONTEXT-1 §5.0, so it's read from the session's
        `intent_context` map directly instead).
        """
        session = SessionManager.get(message)
        key = resolve_key("prev_wiki_article", "private", self.skill_id)
        entry = (session.intent_context or {}).get(key)
        if not isinstance(entry, dict) or not isinstance(entry.get("value"), str):
            return "", []
        title, *chunks = entry["value"].split(_CONTEXT_SEP)
        return title, chunks

    @intent_handler(IntentBuilder("WikiMoreIntent")
                     .require("more").require("prev_wiki_article"))
    def handle_wiki_more_intent(self, message):
        """Follow-up "tell me more" -- speak the next unread chunk of the
        last article looked up via ``handle_search``.

        The gate has no meaning of its own -- "more" is only ever paired
        with the "prev_wiki_article" context set on a successful lookup,
        never satisfied by the utterance alone (a bare "tell me more" with
        nothing looked up first must not fire this handler).
        """
        title, chunks = self._read_prev_wiki_article(message)
        if not chunks:
            self.speak_dialog("nothing.more", {"title": title})
            self.remove_context("prev_wiki_article")
            return
        next_chunk, remaining = chunks[0], chunks[1:]
        self.speak(next_chunk)
        # kept even when `remaining` is empty (rather than removed outright)
        # so the *next* "tell me more" still has the title to speak in
        # nothing.more.dialog, instead of falling back to an empty {title}
        self.set_context("prev_wiki_article",
                          _CONTEXT_SEP.join([title] + remaining),
                          origin="WikiMoreIntent")

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
