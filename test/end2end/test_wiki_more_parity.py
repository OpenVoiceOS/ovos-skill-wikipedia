"""Parity coverage for every "tell me more" phrasing accepted by
``WikiMore.intent`` (the file-intent migration of the Adapt-era
``WikiMoreIntent``, gated on ``more.voc`` + the ``prev_wiki_article``
context). Each phrasing below must resolve to ``handle_wiki_more_intent``
when the session already carries an active "prev_wiki_article" context, and
must NOT be claimed by the skill in a fresh session that never searched
anything -- the same two-sided contract the original Adapt intent enforced.

``_fire()`` captures the session off the skill's own
``mycroft.skill.handler.complete`` done-signal (an existing ``CaptureSession``
EOF marker) rather than reading the orchestrator's private
``SessionManager.sessions`` registry, which is default-session-only per spec
and never holds a named conversation session's real state.
``mycroft.skill.handler.complete`` is used instead of ``ovos.utterance.speak``
because ``handle_search`` speaks BEFORE writing "prev_wiki_article"
(speak-then-set order); ``handler.complete`` fires only after the handler has
fully returned, so it reflects the write regardless of that ordering.
"""
import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_wikipedia import WikipediaResult
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-wikipedia.openvoiceos"
LANG = "en-US"

_PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-medium",
]

_IGNORE = ["mycroft.audio.play_sound"]

# every WikiMore.intent template line, verbatim
MORE_PHRASINGS = [
    "continue",
    "know more",
    "tell me more",
    "tell more",
    "more",
    "more please",
    "tell me more about it",
    "tell me more about that",
    "go on",
    "what else",
    "what else can you tell me",
    "anything else",
    "is there more",
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
    carried_session = session
    for m in messages:
        if m.msg_type == "mycroft.skill.handler.complete" and m.context.get("session"):
            carried_session = Session.deserialize(m.context["session"])
    return spoken, carried_session


@pytest.mark.timeout(60)
@pytest.mark.parametrize("phrasing", MORE_PHRASINGS, ids=MORE_PHRASINGS)
def test_more_phrasing_continues_with_active_context(minicroft, phrasing):
    session = _session(f"parity-positive-{phrasing}")
    first, session = _fire(minicroft, session, "look up Ada Lovelace on wikipedia")
    assert "Ada Lovelace was a mathematician." in first, first

    more, _ = _fire(minicroft, session, phrasing)
    assert "She worked with Charles Babbage." in more, (phrasing, more)


@pytest.mark.timeout(60)
@pytest.mark.parametrize("phrasing", MORE_PHRASINGS, ids=MORE_PHRASINGS)
def test_more_phrasing_does_not_fire_without_prior_context(minicroft, phrasing):
    session = _session(f"parity-negative-{phrasing}")
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [phrasing], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        minicroft,
        eof_msgs=["mycroft.skill.handler.complete", "ovos.intent.unmatched"],
        ignore_messages=_IGNORE,
    )
    capture.capture(utterance, timeout=30)
    types = [m.msg_type for m in capture.finish()]
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"{phrasing!r} with no prior search was claimed by {SKILL_ID}: {types!r}"
