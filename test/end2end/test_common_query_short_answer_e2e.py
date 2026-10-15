"""End-to-end coverage for the common-query path speaking the short answer.

Boots an in-process MiniCroft with the common-query pipeline, stubs the
Wikipedia backend with a two-paragraph intro plus Wikimedia's preview
extract, and checks that a plain question speaks only the preview extract
and that "tell me more" then continues with the second paragraph.

The second turn proves the context write in ``cq_callback`` survives:
``question:action.<skill_id>`` is registered as an intent-like handler, so
its ``mycroft.skill.handler.complete`` carries the updated session, which
is re-declared on the next utterance exactly as a real client would.
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
    "ovos-adapt-pipeline-plugin-high",
    "ovos-common-query-pipeline-plugin",
]

_IGNORE = [
    "mycroft.audio.play_sound",
]

_SHORT = "Ada Lovelace was a mathematician."
_INTRO = ("Ada Lovelace (1815-1852) was a mathematician.\n"
          "She worked with Charles Babbage. She wrote the first published algorithm.")


def _result():
    return WikipediaResult(
        page_id="1",
        lang="en",
        title="Ada Lovelace",
        summary=_INTRO,
        short_summary=_SHORT,
        conf=0.9,
    )


@pytest.fixture(scope="module")
def minicroft():
    # common query is opt-in: ovoscope blacklists every pipeline it isn't told about
    mc = get_minicroft([SKILL_ID], extra_pipelines=["ovos-common-query-pipeline-plugin"])
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


@pytest.mark.timeout(90)
def test_common_query_speaks_short_answer_then_tell_me_more_continues(minicroft):
    session = _session("cq-short-answer")
    first, session = _fire(minicroft, session, "who was ada lovelace")
    assert first == [_SHORT], first

    more, _ = _fire(minicroft, session, "tell me more")
    assert more == ["She worked with Charles Babbage."], more
