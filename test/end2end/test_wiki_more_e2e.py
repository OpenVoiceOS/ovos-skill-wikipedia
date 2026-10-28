"""End-to-end coverage for the "tell me more" follow-up (OVOS-CONTEXT-1
context-gate pattern, mirrors ovos-skill-days-in-history's TellMeMoreIntent).

Boots an in-process MiniCroft with the skill loaded, stubs the Wikipedia
backend with a multi-sentence summary, and drives a search followed by "tell
me more" in the SAME session, so the intent-context write from
``handle_search`` is actually read back by ``WikiMoreIntent`` instead of
being asserted at the unit level only.

``_fire()`` captures the session off the skill's own
``mycroft.skill.handler.complete`` done-signal (the ``CaptureSession`` EOF
marker already used to know the turn is finished) rather than reading the
orchestrator's private ``SessionManager.sessions`` registry: that registry
is default-session-only per spec and never holds a named conversation
session's real state. ``mycroft.skill.handler.complete`` is used instead of
``ovos.utterance.speak`` because both ``handle_search`` and
``handle_wiki_more_intent`` speak BEFORE writing "prev_wiki_article"
(speak-then-set order); ``handler.complete`` only fires once the handler has
fully returned, so it reflects the context write regardless of that
ordering. The captured session is then re-declared on the next turn's
utterance, exactly as a real client would.
"""
import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_wikipedia import WikipediaResult
from ovoscope import CaptureSession
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-wikipedia.openvoiceos"
LANG = "en-US"
WIKI = f"{SKILL_ID}:wiki"
WIKI_MORE = f"{SKILL_ID}:wiki_more"
SKILL_INTENTS = [WIKI, WIKI_MORE, f"{SKILL_ID}:wikiroulette"]

_IGNORE = [
    "mycroft.audio.play_sound",
]


def _result():
    return WikipediaResult(
        page_id="1",
        lang="en",
        title="Ada Lovelace",
        summary=("Ada Lovelace was a mathematician. "
                  "She worked with Charles Babbage. "
                  "She wrote the first published algorithm."),
        best_passage="Ada Lovelace was a mathematician.",
        conf=0.9,
    )


@pytest.fixture(scope="module")
def minicroft():
    mc = get_prototype_minicroft([SKILL_ID], lang=LANG)
    mc.plugin_skills[SKILL_ID].instance.wiki.search = lambda *args, **kwargs: [_result()]
    yield mc
    mc.stop()


def _session(session_id):
    session = Session(session_id)
    session.lang = LANG
    session.pipeline = PIPELINE
    session.blacklisted_intents = []
    return session


def _fire(mc, session, text):
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        mc,
        eof_msgs=["mycroft.skill.handler.complete", "ovos.intent.unmatched"],
        ignore_messages=_IGNORE,
    )
    capture.capture(utterance, timeout=30)
    messages = capture.finish()
    spoken = [m.data.get("utterance", "") for m in messages if m.msg_type == "ovos.utterance.speak"]
    types = [m.msg_type for m in messages]
    carried_session = session
    for m in messages:
        if m.msg_type == "mycroft.skill.handler.complete" and m.context.get("session"):
            carried_session = Session.deserialize(m.context["session"])
    return spoken, types, carried_session


@pytest.mark.timeout(90)
def test_search_then_tell_me_more_continues(minicroft):
    """FAILS on unfixed dev: "tell me more" has no handler at all, so the
    follow-up reaches nothing and the second sentence is never spoken."""
    session = _session("more-flow-positive")
    search = "look up Ada Lovelace on wikipedia"
    first, types, session = _fire(minicroft, session, search)
    TALLY.assert_routed(search, WIKI, types)
    assert "Ada Lovelace was a mathematician." in first, first

    more, types, _ = _fire(minicroft, session, "tell me more")
    TALLY.assert_routed("tell me more", WIKI_MORE, types)
    assert "She worked with Charles Babbage." in more, more


@pytest.mark.timeout(60)
def test_bare_tell_me_more_without_prior_search_does_not_fire_skill(minicroft):
    """A fresh session that never searched anything has no
    "prev_wiki_article" context entry, so WikiMoreIntent's Adapt gate must
    not be satisfiable by the utterance alone."""
    session = _session("more-flow-negative")
    _, types, _ = _fire(minicroft, session, "tell me more")
    TALLY.assert_not_routed("tell me more", SKILL_INTENTS, types)
