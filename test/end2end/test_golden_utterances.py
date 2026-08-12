"""Golden-utterance end-to-end coverage for ovos-skill-wikipedia (en-US).

The golden corpus (``golden_utterances.jsonl``) is a vendored slice of the
shared ovoscope golden-utterance dataset, keyed by
``skill_id == "ovos-skill-wikipedia.openvoiceos"`` (matches this skill's
real OPM entry point too). One shared ``MiniCroft`` (module-scoped fixture)
is booted for the whole suite; every row is its own parametrized test item.

The skill does real network lookups (``WikipediaRetrievalEngine.search`` and
``WikipediaSkill._get_random_page``), so both are monkeypatched for the
duration of the module so routing is exercised offline and deterministically
-- same intent as ``test_intents_en_us.py``, which doesn't stub the network
and so implicitly depends on it. ``_get_random_page`` is patched with a
plain function rather than a bare ``MagicMock``: this skill also registers
it as an app-launcher event handler at load time
(``_register_app_launcher``), which calls ``handler.__name__`` -- a
``MagicMock`` has no real ``__name__`` and raises ``AttributeError``,
breaking skill load entirely (confirmed via isolated instantiation before
settling on this fixture).
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-wikipedia.openvoiceos"
LANG = "en-US"

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

GOLDEN_PATH = Path(__file__).parent / "golden_utterances.jsonl"


def _fake_random_page(self, lang):
    return None


# utterances lifted verbatim from OTHER skills' golden-utterance slices in
# the shared ovoscope corpus, picked for lexical overlap with wikipedia's
# "search"/"find"/"say about"/"tell me" vocabulary. Includes wolfie and
# wordnet -- the wolfie/wikipedia/wordnet trio is the highest cross-skill
# theft risk in this campaign (all three are "look something up" query
# skills) -- documenting and asserting the CURRENT arbitration below.
NEGATIVE_UTTERANCES = [
    ("can you tell me the weather", "ovos-skill-weather.openvoiceos"),
    ("ask the wolf something", "ovos-skill-wolfie.openvoiceos"),
    ("ask wordnet about word", "ovos-skill-wordnet.openvoiceos"),
    ("tell me the word of the day", "ovos-skill-word-of-the-day.openvoiceos"),
    ("search wikihow for something", "ovos-skill-wikihow.openvoiceos"),
    ("can you spell word", "ovos-skill-spelling.openvoiceos"),
    ("set an alarm", "ovos-skill-alerts.openvoiceos"),
]

# wolfie/wikipedia/wordnet cross-arbitration: utterances that plausibly
# belong to one of the OTHER two skills in this trio, fired against THIS
# skill to document and assert the current, actually-observed winner (not
# an assumption). Each entry is (utterance, expected_claimant_skill_id).
# If the expected_claimant is wikipedia itself, it's asserted claimed; if
# it's one of the other two, it's asserted NOT claimed by wikipedia (which
# doesn't prove the other skill claims it -- that's this skill's own suite's
# job -- only that wikipedia doesn't wrongly steal it).
TRIO_ARBITRATION = [
    ("ask the wolfram about something", "ovos-skill-wolfie.openvoiceos"),
    ("search the wolf for something", "ovos-skill-wolfie.openvoiceos"),
    ("search word net for word", "ovos-skill-wordnet.openvoiceos"),
    ("what does word net say about word", "ovos-skill-wordnet.openvoiceos"),
]

# Real, CI-reproduced collision: en-US/wiki.intent's padatious training data
# includes the generic template "search wiki for {query}", which shares
# enough tokens ("search"..."for"...slot) with "search the wolf for
# something" that padatious's fuzzy matcher claims it for wikipedia instead
# of wolfie. Confirmed under CI-pinned padatious; does NOT reproduce in this
# dev venv (no libfann-dev/sudo here to build ovos-padatious, so padacioso --
# a stricter, non-fuzzy matcher -- handles it and correctly does not claim
# it). This is a real, out-of-scope defect (wikipedia's own "search ... for"
# template is too generic), not a corpus mistake, and not blind-edited here
# since there's no local way to verify a template change against padatious.
# Tracked as a strict xfail, gated on padatious actually being installed
# (same shape as the sibling ovos-skill-spelling PR's xfail): a row that
# stops reproducing (env gets padatious and it no longer collides, or the
# template gets fixed) must fail the build.
_TRIO_XFAIL_REASONS = {
    "search the wolf for something": (
        "padatious fuzzy-matches this to wiki.intent via token overlap on "
        "the generic 'search ... for {query}' template shared by several "
        "wiki.intent training lines; reproduces under CI-pinned padatious, "
        "not under the padacioso fallback used in this dev venv."
    ),
}

try:
    import ovos_padatious  # noqa: F401
    _PADATIOUS_INSTALLED = True
except ImportError:
    _PADATIOUS_INSTALLED = False


def _as_trio_param(case):
    text, _claimant = case
    reason = _TRIO_XFAIL_REASONS.get(text)
    if reason is None or not _PADATIOUS_INSTALLED:
        return pytest.param(case, id=text)
    return pytest.param(case, id=text, marks=pytest.mark.xfail(reason=reason, strict=True))


TRIO_PARAMS = [_as_trio_param(c) for c in TRIO_ARBITRATION]


def _matches_intent(msg_type: str, skill_id: str, intent_label: str) -> bool:
    """Tolerant matcher, same shape as the sibling repos' suites: compare
    the ``:``-suffix basename, extension-stripped, so the assertion doesn't
    pin the wire format of any one pipeline plugin."""
    prefix = f"{skill_id}:"
    if not msg_type.startswith(prefix):
        return False
    observed = msg_type[len(prefix):]
    observed_base = observed.rsplit(".", 1)[0] if observed.endswith(".intent") else observed
    expected_base = intent_label.rsplit(".", 1)[0] if intent_label.endswith(".intent") else intent_label
    return observed_base == expected_base


# Rows that do not currently route correctly, with the root-caused reason.
# All xfails are strict=True: a row that starts passing must fail the build.
_XFAIL_REASONS = {}


def _load_golden_rows():
    rows = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


def _as_param(row):
    reason = _XFAIL_REASONS.get(row["utterance"])
    if reason is None:
        return pytest.param(row, id=row["utterance"])
    return pytest.param(row, id=row["utterance"], marks=pytest.mark.xfail(reason=reason, strict=True))


GOLDEN_ROWS = [_as_param(r) for r in _load_golden_rows()]


@pytest.fixture(scope="module")
def minicroft():
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
    mc = get_minicroft([SKILL_ID])
    yield mc
    mc.stop()
    for p in patchers:
        p.stop()


def _types(mc, text, session_id):
    session = Session(session_id)
    session.lang = LANG
    session.pipeline = list(_PIPELINE)
    # blacklisted_intents defaults to None on a fresh Session, which crashes
    # the padacioso pipeline (NoneType membership test) - force an empty list.
    session.blacklisted_intents = []
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
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
    return row["utterance"]


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance(minicroft, row):
    types = _types(minicroft, row["utterance"], f"golden-{_golden_id(row)}")
    assert any(_matches_intent(t, SKILL_ID, row["intent_label"]) for t in types), (
        f"{row['utterance']!r}: expected {SKILL_ID}:{row['intent_label']}, got {types!r}"
    )


@pytest.mark.timeout(60)
@pytest.mark.parametrize("negative", NEGATIVE_UTTERANCES, ids=lambda n: n[0])
def test_negative_confusable_not_claimed(minicroft, negative):
    text, source_skill = negative
    types = _types(minicroft, text, f"negative-{text}")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"{text!r} (from {source_skill}) was incorrectly claimed by {SKILL_ID}"


@pytest.mark.timeout(60)
@pytest.mark.parametrize("case", TRIO_PARAMS)
def test_trio_arbitration_not_claimed_by_wikipedia(minicroft, case):
    text, expected_claimant = case
    assert expected_claimant != SKILL_ID, "this list is for utterances belonging to the OTHER two skills"
    types = _types(minicroft, text, f"trio-{text}")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, (
        f"{text!r} (expected to belong to {expected_claimant}) was incorrectly claimed by {SKILL_ID}"
    )
