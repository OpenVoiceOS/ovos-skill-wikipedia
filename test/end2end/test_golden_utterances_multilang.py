"""Golden-utterance end-to-end coverage for ovos-skill-wikipedia, every locale.

Every ``golden_utterances_<lang>.jsonl`` in this directory is loaded, and every
row runs, including rows marked ``needs_manual`` (machine-generated rows that
no native speaker vouched for). Each row asserts that its ``intent_label`` is
the intent the pipeline matched. ``{query}`` rows are filled with an obvious
loanword (pizza / yoga).

``wiki_more.intent`` requires the "prev_wiki_article" shared session context
(``requires_context`` on the handler, see ``__init__.py``). A real search opens
that context with ``Session.set_intent_context``; rows marked
``requires_context`` open it the same way on the session before the utterance,
so the gated intent is exercised with its gate satisfied.

One MiniCroft is booted per locale in turn (lang=<locale>, no
secondary_langs). The skill does real network lookups; both
``WikipediaRetrievalEngine.search`` and ``WikipediaSkill._get_random_page``
are monkeypatched module-wide for the duration of the test run, same as the
en-US suite.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-wikipedia.openvoiceos"

_PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-medium",
]

_IGNORE = [
    "speak",
    "ovos.utterance.speak",
    "mycroft.audio.play_sound",
]

END2END_DIR = Path(__file__).parent

LANGS = sorted(p.stem.removeprefix("golden_utterances_")
               for p in END2END_DIR.glob("golden_utterances_*.jsonl"))

PREV_WIKI_ARTICLE_CONTEXT = "prev_wiki_article"
_CONTEXT_SEP = "\x1f"


def _fake_random_page(self, lang):
    return None


def _matches_intent(msg_type: str, skill_id: str, intent_label: str) -> bool:
    prefix = f"{skill_id}:"
    if not msg_type.startswith(prefix):
        return False
    observed = msg_type[len(prefix):]
    observed_base = observed.rsplit(".", 1)[0] if observed.endswith(".intent") else observed
    expected_base = intent_label.rsplit(".", 1)[0] if intent_label.endswith(".intent") else intent_label
    return observed_base == expected_base


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


ALL_ROWS = []
for _lang in LANGS:
    for _row in _load_rows(_lang):
        ALL_ROWS.append(_row)


def _as_param(row):
    gated = "gated" if row.get("requires_context") else "tier2"
    return pytest.param(row, id=f"{row['lang']}-{gated}-{row['intent_label']}-{row['utterance']}")


GOLDEN_ROWS = [_as_param(r) for r in ALL_ROWS]

_BOOTED = {}
_PATCHERS_STARTED = False


@pytest.fixture(scope="module")
def mc_factory(request):
    global _PATCHERS_STARTED
    if not _PATCHERS_STARTED:
        patchers = [
            patch("ovos_skill_wikipedia.WikipediaRetrievalEngine.search", return_value=[]),
            patch.object(
                __import__("ovos_skill_wikipedia").WikipediaSkill,
                "_get_random_page",
                _fake_random_page,
            ),
        ]
        for p in patchers:
            p.start()
        _PATCHERS_STARTED = True
        request.addfinalizer(lambda: [p.stop() for p in patchers])

    def _get(lang):
        if lang not in _BOOTED:
            mc = get_minicroft([SKILL_ID], max_wait=150, lang=lang)
            _BOOTED[lang] = mc
            request.addfinalizer(mc.stop)
        return _BOOTED[lang]
    return _get


def _types(mc, text, lang, session_id, with_context=False):
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(_PIPELINE)
    session.blacklisted_intents = []
    if with_context:
        session.set_intent_context(PREV_WIKI_ARTICLE_CONTEXT,
                                   _CONTEXT_SEP.join(["Pizza", "Pizza is a dish."]),
                                   scope="shared", turns_remaining=3)
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        mc,
        eof_msgs=["mycroft.skill.handler.start", "ovos.intent.unmatched"],
        ignore_messages=_IGNORE,
    )
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


def _golden_id(row):
    return f"{row['lang']}-{row['intent_label']}-{row['utterance']}"


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance_multilang(mc_factory, row):
    mc = mc_factory(row["lang"])
    types = _types(mc, row["utterance"], row["lang"], f"golden-{_golden_id(row)}",
                   with_context=bool(row.get("requires_context")))
    assert any(_matches_intent(t, SKILL_ID, row["intent_label"]) for t in types), (
        f"[{row['lang']}] {row['utterance']!r}: expected {SKILL_ID}:{row['intent_label']}, got {types!r}"
    )
