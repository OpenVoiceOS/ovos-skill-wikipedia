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
from ovos_utils import classproperty
from ovos_utils.process_utils import RuntimeRequirements
from ovos_wikipedia import WikipediaRetrievalEngine, WikipediaResult
from ovos_workshop.decorators import intent_handler, common_query
from ovos_workshop.skills.ovos import OVOSSkill

# OVOS-CONTEXT-1 shared-scope key holding the title + unread sentence chunks
# of the last article looked up, so a follow-up "tell me more" can continue
# reading it. Session context values are opaque JSON-able payloads (not
# limited to adapt-engine's plain context words), so title and chunks are
# packed on this separator into one string rather than needing a dict.
PREV_WIKI_ARTICLE_CONTEXT = "prev_wiki_article"
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

        ``spoken`` is the full summary (nothing left), a QA-selected
        passage drawn verbatim from within it, or Wikimedia's preview
        extract of the lead paragraph (re-cleaned upstream, so it rarely
        matches the intro text verbatim: the first paragraph is skipped).
        """
        text = summary or ""
        if spoken and spoken == text:
            text = ""
        elif spoken and spoken in text:
            text = text.replace(spoken, "", 1)
        elif spoken:
            text = text.split("\n", 1)[1] if "\n" in text else ""
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    @staticmethod
    def _spoken_answer(result: WikipediaResult) -> str:
        """Shortest faithful answer available: a QA-extracted passage, then
        Wikimedia's preview extract, then the full intro."""
        return result.best_passage or result.short_summary or result.summary

    def _remember_unread(self, sess, result: WikipediaResult, spoken: str):
        """Leave whatever of the article was not spoken for "tell me more"."""
        chunks = self._remaining_chunks(result.summary, spoken)
        if chunks:
            sess.set_intent_context(PREV_WIKI_ARTICLE_CONTEXT,
                                     _CONTEXT_SEP.join([result.title] + chunks),
                                     scope="shared", turns_remaining=3)

    # explicit wikipedia requests
    @intent_handler("wiki.intent")
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
            spoken = self._spoken_answer(best)
            self.speak(spoken)
            self._remember_unread(sess, best, spoken)
        else:
            self.speak_dialog("no_answer")

    @staticmethod
    def _read_prev_wiki_article(session) -> Tuple[str, List[str]]:
        """Read the "prev_wiki_article" OVOS-CONTEXT-1 shared-scope entry
        back out of the session."""
        entry = (session.intent_context or {}).get(PREV_WIKI_ARTICLE_CONTEXT)
        if not isinstance(entry, dict) or not isinstance(entry.get("value"), str):
            return "", []
        title, *chunks = entry["value"].split(_CONTEXT_SEP)
        return title, chunks

    @intent_handler("wiki_more.intent",
                     requires_context=[{"key": PREV_WIKI_ARTICLE_CONTEXT, "scope": "shared"}])
    def handle_wiki_more_intent(self, message):
        """Follow-up "tell me more" -- speak the next unread chunk of the
        last article looked up via ``handle_search``.

        Gated on OVOS-CONTEXT-1 ``requires_context`` rather than a keyword
        vocab: "tell me more" has no meaning of its own, it only fires as a
        follow-up to a lookup that already set "prev_wiki_article" (a bare
        "tell me more" with nothing looked up first must not fire this
        handler).
        """
        session = SessionManager.get(message)
        title, chunks = self._read_prev_wiki_article(session)
        if not chunks:
            self.speak_dialog("nothing_more", {"title": title})
            session.remove_intent_context(PREV_WIKI_ARTICLE_CONTEXT, scope="shared")
            return
        next_chunk, remaining = chunks[0], chunks[1:]
        self.speak(next_chunk)
        # kept even when `remaining` is empty (rather than removed outright)
        # so the *next* "tell me more" still has the title to speak in
        # nothing_more.dialog, instead of falling back to an empty {title}
        session.set_intent_context(PREV_WIKI_ARTICLE_CONTEXT,
                                    _CONTEXT_SEP.join([title] + remaining),
                                    scope="shared", turns_remaining=3)

    def _get_random_page(self, lang: str) -> Optional[WikipediaResult]:
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {"action": "query", "list": "random", "rnnamespace": 0, "rnlimit": 1, "format": "json"}
        try:
            resp = requests.get(url, params=params, timeout=10, headers={"User-Agent": self.wiki.USER_AGENT})
            resp.raise_for_status()
            page = resp.json()["query"]["random"][0]
            result = self.wiki._get_page_data(str(page["id"]), lang)
        except Exception:
            return None
        if result:
            result.short_summary = self.wiki._get_short_summary(result.title, lang)
        return result

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
            spoken = self._spoken_answer(result)
            self.speak(result.title + ". " + spoken)
            self._remember_unread(sess, result, spoken)
            if sess.session_id == "default" and result.image:
                self.gui.show_image(result.image)
        else:
            self.speak_dialog("no_answer")

    # common query
    def cq_callback(self, utterance: str, answer: str, lang: str):
        """ If selected, show gui and keep the rest of the article for "tell me more" """
        sess = SessionManager.get()
        cached = self.session_results.get(sess.session_id, {})
        if cached.get("image"):
            self.gui.show_image(cached["image"])
        if cached.get("results"):
            self._remember_unread(sess, cached["results"][0], answer)

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
            answer = self._spoken_answer(best)
            self.log.info(f"Wikipedia answer: {answer}")
            self.session_results[sess.session_id]["results"] = results
            self.session_results[sess.session_id]["image"] = best.image
            return answer, best.conf
