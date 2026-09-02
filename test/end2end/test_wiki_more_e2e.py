"""End-to-end coverage for the "tell me more" follow-up (OVOS-CONTEXT-1
context-gate pattern, mirrors ovos-skill-days-in-history's TellMeMoreIntent).

Boots an in-process MiniCroft with the skill loaded, stubs the Wikipedia
backend with a multi-sentence summary, and drives the real
padatious/padacioso + adapt pipelines through a search followed by "tell me
more" in the SAME session, so the intent-context write from
``handle_search`` is actually read back by ``WikiMoreIntent`` instead of
being asserted at the unit level only.

``_fire()`` looks the live session back up in ``SessionManager.sessions``
after a turn completes, since the context write happens server-side on the
``SessionManager`` registry singleton, not on the caller's local ``Session``
snapshot (same shape as the sibling wallpapers-skill slideshow-gate suite).
"""
from unittest.mock import patch

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session, SessionManager
from ovos_wikipedia import WikipediaResult
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-wikipedia.openvoiceos"
LANG = "en-US"

_PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-medium",
    "ovos-adapt-pipeline-plugin-medium",
]

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
    mc = get_minicroft([SKILL_ID])
    mc.plugin_skills[SKILL_ID].instance.wiki.search = lambda *args, **kwargs: [_result()]
    yield mc
    mc.stop()


def _session(session_id):
    session = Session(session_id)
    session.lang = LANG
    session.pipeline = list(_PIPELINE)
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
    live_session = SessionManager.sessions.get(session.session_id, session)
    return spoken, types, live_session


@pytest.mark.timeout(90)
def test_search_then_tell_me_more_continues(minicroft):
    """FAILS on unfixed dev: "tell me more" has no handler at all, so the
    follow-up reaches nothing and the second sentence is never spoken."""
    session = _session("more-flow-positive")
    first, _, session = _fire(minicroft, session, "look up Ada Lovelace on wikipedia")
    assert "Ada Lovelace was a mathematician." in first, first

    more, _, _ = _fire(minicroft, session, "tell me more")
    assert "She worked with Charles Babbage." in more, more


@pytest.mark.timeout(60)
def test_bare_tell_me_more_without_prior_search_does_not_fire_skill(minicroft):
    """A fresh session that never searched anything has no
    "prev_wiki_article" context entry, so WikiMoreIntent's Adapt gate must
    not be satisfiable by the utterance alone."""
    session = _session("more-flow-negative")
    _, types, _ = _fire(minicroft, session, "tell me more")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"'tell me more' with no prior search was claimed by {SKILL_ID}: {types!r}"
