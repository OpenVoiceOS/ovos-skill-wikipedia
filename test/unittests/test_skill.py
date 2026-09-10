"""
Unit tests for WikipediaSkill.

Uses FakeBus and mocked WikipediaRetrievalEngine — no network, no OVOS daemon required.
"""
import unittest
from unittest.mock import MagicMock, patch, call

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_utils.fakebus import FakeBus
from ovos_wikipedia import WikipediaResult


def _make_result(title="Python", summary="Python is a language.", conf=0.8, image=None, best_passage=None):
    r = WikipediaResult(page_id="1", lang="en", title=title, summary=summary, conf=conf)
    r.image = image
    r.best_passage = best_passage
    return r


_PRONOUN_WORDS = ["he", "him", "his", "she", "her", "hers", "it", "its", "they",
                  "them", "their", "theirs", "that", "this", "those", "these"]


def _pronoun_voc_list(voc_filename, lang=None):
    return _PRONOUN_WORDS if voc_filename == "pronoun" else []


def _make_skill():
    with patch("ovos_wikipedia.WikipediaRetrievalEngine") as mock_engine_cls:
        from ovos_skill_wikipedia import WikipediaSkill
        bus = FakeBus()
        skill = WikipediaSkill(bus=bus, skill_id="test.wikipedia")
        skill.wiki = mock_engine_cls.return_value
        return skill


# ---------------------------------------------------------------------------
# Skill instantiation
# ---------------------------------------------------------------------------

class TestSkillInit(unittest.TestCase):

    def test_skill_creates_wiki_engine(self):
        with patch("ovos_skill_wikipedia.WikipediaRetrievalEngine") as mock_cls:
            from ovos_skill_wikipedia import WikipediaSkill
            skill = WikipediaSkill(bus=FakeBus(), skill_id="test.wikipedia")
        mock_cls.assert_called_once()

    def test_session_results_starts_empty(self):
        skill = _make_skill()
        self.assertEqual(skill.session_results, {})

    def test_runtime_requires_internet(self):
        skill = _make_skill()
        req = skill.runtime_requirements
        self.assertTrue(req.requires_internet)
        self.assertTrue(req.internet_before_load)
        self.assertFalse(req.no_internet_fallback)


# ---------------------------------------------------------------------------
# handle_search — explicit intent handler
# ---------------------------------------------------------------------------

class TestHandleSearch(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill.speak = MagicMock()
        self.skill.speak_dialog = MagicMock()
        self.skill.gui = MagicMock()

    def _message(self, query="Ada Lovelace"):
        return Message("ovos.skills.test", data={"query": query})

    def test_speaks_summary_when_no_best_passage(self):
        result = _make_result(summary="Ada was a mathematician.", best_passage=None)
        self.skill.wiki.search.return_value = [result]
        self.skill.handle_search(self._message("Ada Lovelace"))
        self.skill.speak.assert_called_once_with("Ada was a mathematician.")

    def test_speaks_best_passage_when_available(self):
        result = _make_result(summary="Long summary.", best_passage="Short passage.")
        self.skill.wiki.search.return_value = [result]
        self.skill.handle_search(self._message("Ada Lovelace"))
        self.skill.speak.assert_called_once_with("Short passage.")

    def test_speaks_no_answer_when_no_results(self):
        self.skill.wiki.search.return_value = []
        self.skill.handle_search(self._message("xyzzy"))
        self.skill.speak_dialog.assert_any_call("no_answer")

    def test_speaks_searching_dialog_first(self):
        self.skill.wiki.search.return_value = [_make_result()]
        self.skill.handle_search(self._message("Ada Lovelace"))
        self.skill.speak_dialog.assert_called_once_with("searching", {"query": "Ada Lovelace"})

    def test_search_called_with_query_and_lang(self):
        self.skill.wiki.search.return_value = [_make_result()]
        self.skill.handle_search(self._message("Ada Lovelace"))
        self.skill.wiki.search.assert_called_once()
        args = self.skill.wiki.search.call_args
        self.assertEqual(args[0][0], "Ada Lovelace")

    def test_gui_shown_for_default_session(self):
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "default"
            mock_sm.get.return_value.lang = "en-US"
            self.skill.wiki.search.return_value = [_make_result()]
            self.skill.handle_search(self._message("Ada Lovelace"))
        self.skill.gui.show_animated_image.assert_called_once_with("jumping.gif")

    def test_gui_not_shown_for_non_default_session(self):
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "remote-xyz"
            mock_sm.get.return_value.lang = "en-US"
            self.skill.wiki.search.return_value = [_make_result()]
            self.skill.handle_search(self._message("Ada Lovelace"))
        self.skill.gui.show_animated_image.assert_not_called()

    def test_anaphoric_slot_value_is_not_searched(self):
        self.skill.voc_list = MagicMock(return_value=["he", "him", "her", "it", "they"])
        self.skill.wiki.search.return_value = [_make_result()]
        self.skill.handle_search(self._message("him"))
        self.skill.wiki.search.assert_not_called()
        self.skill.speak_dialog.assert_called_once_with("no_query")

    def test_non_anaphoric_slot_value_is_searched(self):
        self.skill.voc_list = MagicMock(return_value=["he", "him", "her", "it", "they"])
        self.skill.wiki.search.return_value = [_make_result()]
        self.skill.handle_search(self._message("Ada Lovelace"))
        self.skill.wiki.search.assert_called_once()

    def test_title_containing_pronoun_word_is_not_excluded(self):
        """"the it crowd" / "her majesty" are real titles: the check is an
        exact match against the whole {query} value, never a containment
        test, so they must still be searched."""
        self.skill.voc_list = MagicMock(return_value=["he", "him", "her", "it", "they"])
        self.skill.wiki.search.return_value = [_make_result()]
        self.skill.handle_search(self._message("the it crowd"))
        self.skill.wiki.search.assert_called_once()
        self.skill.handle_search(self._message("her majesty"))
        self.assertEqual(self.skill.wiki.search.call_count, 2)

    def test_empty_query_reprompts(self):
        self.skill.voc_list = MagicMock(return_value=["he", "him", "her", "it", "they"])
        self.skill.wiki.search.return_value = [_make_result()]
        self.skill.handle_search(self._message(""))
        self.skill.wiki.search.assert_not_called()
        self.skill.speak_dialog.assert_called_once_with("no_query")


# ---------------------------------------------------------------------------
# match_common_query
# ---------------------------------------------------------------------------

class TestMatchCommonQuery(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill.speak = MagicMock()
        self.skill.gui = MagicMock()
        self.skill.voc_match = MagicMock(return_value=False)

    def test_returns_summary_and_conf(self):
        result = _make_result(summary="Python is a language.", conf=0.85)
        self.skill.wiki.search.return_value = [result]
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "s1"
            mock_sm.get.return_value.lang = "en-US"
            ret = self.skill.match_common_query("what is python", "en-US")
        self.assertEqual(ret, ("Python is a language.", 0.85))

    def test_returns_none_when_no_results(self):
        self.skill.wiki.search.return_value = []
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "s1"
            mock_sm.get.return_value.lang = "en-US"
            ret = self.skill.match_common_query("xyzzy nonsense", "en-US")
        self.assertIsNone(ret)

    def test_returns_none_for_misc_blacklist(self):
        self.skill.voc_match.side_effect = lambda phrase, voc: voc == "misc_blacklist"
        ret = self.skill.match_common_query("how do you install this", "en-US")
        self.assertIsNone(ret)
        self.skill.wiki.search.assert_not_called()

    def test_returns_none_for_weather_query(self):
        self.skill.voc_match.side_effect = lambda phrase, voc: voc == "weather"
        ret = self.skill.match_common_query("what is the weather today", "en-US")
        self.assertIsNone(ret)
        self.skill.wiki.search.assert_not_called()

    def test_returns_none_for_bare_anaphora(self):
        """"he" has no article to look up and must never reach the
        live wikipedia search."""
        self.skill.voc_list = MagicMock(return_value=["he", "him", "her", "it", "they"])
        ret = self.skill.match_common_query("he", "en-US")
        self.assertIsNone(ret)
        self.skill.wiki.search.assert_not_called()

    def _use_real_voc_match(self):
        """Restore the real (unmocked) ``voc_match`` implementation, backed
        by a stubbed ``voc_list`` -- so these tests exercise the actual
        containment-vs-exact-match semantics instead of an always-False
        stand-in that can't tell the buggy and fixed code apart."""
        from ovos_skill_wikipedia import WikipediaSkill
        self.skill.voc_match = WikipediaSkill.voc_match.__get__(self.skill, WikipediaSkill)
        self.skill.voc_list = MagicMock(side_effect=_pronoun_voc_list)

    def test_who_is_her_majesty_is_answered(self):
        """"her majesty" is a real article title; the anaphora guard must
        not reject it just because it contains the pronoun word "her"."""
        self._use_real_voc_match()
        result = _make_result(summary="Elizabeth II was a monarch.", conf=0.9)
        self.skill.wiki.search.return_value = [result]
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "s6"
            mock_sm.get.return_value.lang = "en-US"
            ret = self.skill.match_common_query("who is her majesty", "en-US")
        self.assertEqual(ret, ("Elizabeth II was a monarch.", 0.9))

    def test_what_is_the_it_crowd_is_answered(self):
        self._use_real_voc_match()
        result = _make_result(summary="A British sitcom.", conf=0.9)
        self.skill.wiki.search.return_value = [result]
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "s7"
            mock_sm.get.return_value.lang = "en-US"
            ret = self.skill.match_common_query("what is the it crowd", "en-US")
        self.assertEqual(ret, ("A British sitcom.", 0.9))

    def test_tell_me_about_his_dark_materials_is_answered(self):
        self._use_real_voc_match()
        result = _make_result(summary="A fantasy trilogy.", conf=0.9)
        self.skill.wiki.search.return_value = [result]
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "s8"
            mock_sm.get.return_value.lang = "en-US"
            ret = self.skill.match_common_query("tell me about his dark materials", "en-US")
        self.assertEqual(ret, ("A fantasy trilogy.", 0.9))

    def test_who_is_he_still_declined(self):
        self._use_real_voc_match()
        ret = self.skill.match_common_query("who is he", "en-US")
        self.assertIsNone(ret)
        self.skill.wiki.search.assert_not_called()

    def test_what_about_it_still_declined(self):
        self._use_real_voc_match()
        ret = self.skill.match_common_query("what about it", "en-US")
        self.assertIsNone(ret)
        self.skill.wiki.search.assert_not_called()

    def test_real_question_still_answered(self):
        self.skill.voc_match.return_value = False
        result = _make_result(summary="Ada was a mathematician.", conf=0.9)
        self.skill.wiki.search.return_value = [result]
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "s5"
            mock_sm.get.return_value.lang = "en-US"
            ret = self.skill.match_common_query("who is ada lovelace", "en-US")
        self.assertEqual(ret, ("Ada was a mathematician.", 0.9))

    def test_stores_image_in_session_results(self):
        result = _make_result(image="http://img.example.com/pic.jpg")
        self.skill.wiki.search.return_value = [result]
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "s2"
            mock_sm.get.return_value.lang = "en-US"
            self.skill.match_common_query("Ada Lovelace", "en-US")
        self.assertEqual(self.skill.session_results["s2"]["image"], "http://img.example.com/pic.jpg")

    def test_stores_none_image_when_no_image(self):
        result = _make_result(image=None)
        self.skill.wiki.search.return_value = [result]
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "s3"
            mock_sm.get.return_value.lang = "en-US"
            self.skill.match_common_query("Ada Lovelace", "en-US")
        self.assertIsNone(self.skill.session_results["s3"]["image"])

    def test_search_called_with_phrase_and_session_lang(self):
        result = _make_result()
        self.skill.wiki.search.return_value = [result]
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "s4"
            mock_sm.get.return_value.lang = "pt-PT"
            self.skill.match_common_query("Ada Lovelace", "pt-PT")
        self.skill.wiki.search.assert_called_once_with("Ada Lovelace", lang="pt-PT")


# ---------------------------------------------------------------------------
# cq_callback
# ---------------------------------------------------------------------------

class TestCqCallback(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill.gui = MagicMock()

    def test_shows_image_when_available(self):
        self.skill.session_results["sess"] = {"image": "http://img/pic.jpg"}
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "sess"
            self.skill.cq_callback("query", "answer", "en-US")
        self.skill.gui.show_image.assert_called_once_with("http://img/pic.jpg")

    def test_no_image_shown_when_none(self):
        self.skill.session_results["sess"] = {"image": None}
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "sess"
            self.skill.cq_callback("query", "answer", "en-US")
        self.skill.gui.show_image.assert_not_called()

    def test_no_image_shown_for_unknown_session(self):
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "unknown"
            self.skill.cq_callback("query", "answer", "en-US")
        self.skill.gui.show_image.assert_not_called()


# ---------------------------------------------------------------------------
# WikiRoulette
# ---------------------------------------------------------------------------

class TestWikiRoulette(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill.speak = MagicMock()
        self.skill.speak_dialog = MagicMock()
        self.skill.gui = MagicMock()

    def _message(self):
        return Message("ovos.skills.test", data={})

    def test_get_random_page_returns_result(self):
        fake_api = {"query": {"random": [{"id": 42, "title": "Banana"}]}}
        result = _make_result(title="Banana", summary="Banana is a fruit.")
        self.skill.wiki._get_page_data.return_value = result
        with patch("ovos_skill_wikipedia.requests.get") as mock_get:
            mock_get.return_value.json.return_value = fake_api
            mock_get.return_value.raise_for_status = MagicMock()
            ret = self.skill._get_random_page("en")
        self.assertEqual(ret, result)
        self.skill.wiki._get_page_data.assert_called_once_with("42", "en")

    def test_get_random_page_returns_none_on_error(self):
        with patch("ovos_skill_wikipedia.requests.get") as mock_get:
            mock_get.side_effect = Exception("network error")
            ret = self.skill._get_random_page("en")
        self.assertIsNone(ret)

    def test_handle_roulette_speaks_title_and_summary(self):
        result = _make_result(title="Banana", summary="Banana is a fruit.", best_passage=None)
        self.skill._get_random_page = MagicMock(return_value=result)
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "default"
            mock_sm.get.return_value.lang = "en-US"
            self.skill.handle_wiki_roulette_query(self._message())
        self.skill.speak.assert_called_once_with("Banana. Banana is a fruit.")

    def test_handle_roulette_speaks_best_passage_if_available(self):
        result = _make_result(title="Banana", summary="Long summary.", best_passage="Short.")
        self.skill._get_random_page = MagicMock(return_value=result)
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "default"
            mock_sm.get.return_value.lang = "en-US"
            self.skill.handle_wiki_roulette_query(self._message())
        self.skill.speak.assert_called_once_with("Banana. Short.")

    def test_handle_roulette_speaks_no_answer_when_none(self):
        self.skill._get_random_page = MagicMock(return_value=None)
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "default"
            mock_sm.get.return_value.lang = "en-US"
            self.skill.handle_wiki_roulette_query(self._message())
        self.skill.speak_dialog.assert_any_call("no_answer")

    def test_handle_roulette_shows_image_for_default_session(self):
        result = _make_result(title="Banana", summary="A fruit.", image="http://img/banana.jpg")
        self.skill._get_random_page = MagicMock(return_value=result)
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "default"
            mock_sm.get.return_value.lang = "en-US"
            self.skill.handle_wiki_roulette_query(self._message())
        self.skill.gui.show_image.assert_called_once_with("http://img/banana.jpg")

    def test_handle_roulette_no_image_for_remote_session(self):
        result = _make_result(title="Banana", summary="A fruit.", image="http://img/banana.jpg")
        self.skill._get_random_page = MagicMock(return_value=result)
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value.session_id = "remote-xyz"
            mock_sm.get.return_value.lang = "en-US"
            self.skill.handle_wiki_roulette_query(self._message())
        self.skill.gui.show_image.assert_not_called()


# ---------------------------------------------------------------------------
# "tell me more" context chaining
# ---------------------------------------------------------------------------

class TestWikiMoreContext(unittest.TestCase):

    def setUp(self):
        self.skill = _make_skill()
        self.skill.speak = MagicMock()
        self.skill.speak_dialog = MagicMock()
        self.skill.gui = MagicMock()

    def _message(self, query="Ada Lovelace"):
        return Message("ovos.skills.test", data={"query": query})

    def _prime_context(self, session, title, chunks):
        """Write "prev_wiki_article" the same way ``session.set_intent_context``
        does: OVOS-CONTEXT-1 shared scope, packed on the same separator."""
        session.intent_context = {
            "prev_wiki_article": {"value": "\x1f".join([title] + chunks)}
        }

    def test_handle_search_sets_context_when_summary_has_leftover_sentences(self):
        result = _make_result(
            summary="Ada was a mathematician. She worked with Babbage. She wrote the first algorithm.",
            best_passage="Ada was a mathematician.",
            title="Ada Lovelace",
        )
        self.skill.wiki.search.return_value = [result]
        session = Session("s-more-1")
        session.lang = "en-US"
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value = session
            self.skill.handle_search(self._message())
        entry = session.intent_context["prev_wiki_article"]
        self.assertEqual(
            entry["value"],
            "Ada Lovelace\x1fShe worked with Babbage.\x1fShe wrote the first algorithm.",
        )

    def test_handle_search_sets_no_context_when_nothing_left(self):
        result = _make_result(summary="Ada was a mathematician.", best_passage=None, title="Ada Lovelace")
        self.skill.wiki.search.return_value = [result]
        session = Session("s-more-2")
        session.lang = "en-US"
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value = session
            self.skill.handle_search(self._message())
        self.assertNotIn("prev_wiki_article", session.intent_context or {})

    def test_wiki_more_speaks_next_chunk_and_keeps_context(self):
        session = Session("s-more-3")
        self._prime_context(session, "Ada Lovelace", ["First more bit.", "Second more bit."])
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value = session
            self.skill.handle_wiki_more_intent(self._message())
        self.skill.speak.assert_called_once_with("First more bit.")
        entry = session.intent_context["prev_wiki_article"]
        self.assertEqual(entry["value"], "Ada Lovelace\x1fSecond more bit.")

    def test_wiki_more_exhausts_and_speaks_nothing_more_dialog(self):
        session = Session("s-more-4")
        self._prime_context(session, "Ada Lovelace", ["Last bit."])
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value = session
            self.skill.handle_wiki_more_intent(self._message())
        self.skill.speak.assert_called_once_with("Last bit.")
        entry = session.intent_context["prev_wiki_article"]
        self.assertEqual(entry["value"], "Ada Lovelace")

        # a second "more" call sees the now-empty chunk list this write
        # produced, and speaks the exhaustion dialog with the title intact
        self._prime_context(session, "Ada Lovelace", [])
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value = session
            self.skill.handle_wiki_more_intent(self._message())
        self.skill.speak_dialog.assert_called_once_with(
            "nothing.more", {"title": "Ada Lovelace"})
        self.assertIsNone(session.intent_context["prev_wiki_article"])

    def test_wiki_more_without_context_speaks_nothing_more_dialog(self):
        session = Session("s-more-5")
        with patch("ovos_skill_wikipedia.SessionManager") as mock_sm:
            mock_sm.get.return_value = session
            self.skill.handle_wiki_more_intent(self._message())
        self.skill.speak_dialog.assert_called_once_with("nothing.more", {"title": ""})
        self.skill.speak.assert_not_called()


if __name__ == "__main__":
    unittest.main()
