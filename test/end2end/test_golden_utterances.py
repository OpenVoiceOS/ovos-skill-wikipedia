"""Golden rows route to their intent on the m2v prototype pipeline, and
negative rows reach no intent of this skill."""
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope.routing import TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-wikipedia.openvoiceos"
END2END_DIR = Path(__file__).parent


def _rows(prefix):
    rows = []
    for path in sorted(END2END_DIR.glob(f"{prefix}*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    return rows


GOLDEN = _rows("golden_utterances_")
NEGATIVE = _rows("negative_utterances_")
_booted = {}


@pytest.fixture(scope="module")
def engine_for():
    def engine(lang):
        if lang not in _booted:
            for minicroft in _booted.values():
                minicroft.stop()
            _booted.clear()
            _booted[lang] = get_prototype_minicroft([SKILL_ID], lang=lang)
        return _booted[lang].intents.pipeline_plugins["ovos-m2v-prototype-pipeline"]
    yield engine
    for minicroft in _booted.values():
        minicroft.stop()


def _routed(engine, row):
    session = Session(lang=row["lang"])
    if row.get("requires_context"):
        session.set_intent_context("prev_wiki_article", "a page", scope="shared")
    message = Message("recognizer_loop:utterance",
                      {"utterances": [row["utterance"]], "lang": row["lang"]},
                      {"lang": row["lang"], "session": session.serialize()})
    match = engine.match_low([row["utterance"]], row["lang"], message)
    return [match.match_type] if match else []


def _row_id(row):
    return f"{row['lang']}:{row['utterance']}"


@pytest.mark.parametrize("row", GOLDEN, ids=_row_id)
def test_golden_row_routes_to_its_intent(engine_for, row):
    fired = _routed(engine_for(row["lang"]), row)
    TALLY.assert_routed(row["utterance"], f"{SKILL_ID}:{row['intent_label']}", fired)


@pytest.mark.parametrize("row", NEGATIVE, ids=_row_id)
def test_negative_row_reaches_no_intent_of_the_skill(engine_for, row):
    fired = _routed(engine_for(row["lang"]), row)
    TALLY.assert_not_routed(row["utterance"],
                            [t for t in fired if t.startswith(f"{SKILL_ID}:")], fired)
