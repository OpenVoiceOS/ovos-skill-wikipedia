# ovos-skill-wikipedia

[![PyPI](https://img.shields.io/pypi/v/ovos-skill-wikipedia)](https://pypi.org/project/ovos-skill-wikipedia/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue)](https://www.python.org/)

Wikipedia skill for [OpenVoiceOS](https://openvoiceos.org). Adds a voice interface on top of [ovos-wikipedia-plugin](https://github.com/OpenVoiceOS/ovos-wikipedia-solver), which handles all Wikipedia search and retrieval.

Supports two answer modes:
- **Direct intent** — responds to explicit requests like "tell me about X" or "search Wikipedia for X"
- **Common Query** — participates in the [OVOS Common Query pipeline](https://github.com/OpenVoiceOS/ovos-common-query-pipeline-plugin) alongside other knowledge skills; the best answer wins

---

## Installation

```bash
pip install ovos-skill-wikipedia
```

---

## Example utterances

- "Tell me about Elon Musk"
- "Tell me about beans"
- "Check Wikipedia for beans"
- "Tell me about the Pembroke Welsh Corgi"
- "Search for chocolate"

---

## Common Query pipeline

When the [Common Query pipeline plugin](https://github.com/OpenVoiceOS/ovos-common-query-pipeline-plugin) is active, this skill competes against other knowledge skills (e.g. Wolfram Alpha, WordNet) to answer general questions. The pipeline selects the response with the highest confidence score.

To enable, add to `mycroft.conf`:

```json
{
  "intents": {
    "pipeline": [
      "...",
      "common_query_high",
      "...",
      "common_query_low"
    ]
  }
}
```

Optionally, configure a reranker to improve answer selection across skills:

```json
{
  "intents": {
    "common_query": {
      "min_reranker_score": 0.5,
      "reranker": "ovos-flashrank-reranker-plugin"
    }
  }
}
```

---

## Sub-plugins

All sub-plugins are optional. Configure them via `~/.config/mycroft/skills/ovos-skill-wikipedia.openvoiceos/settings.json`:

```json
{
  "extractive_qa": "ovos-bm25-solver",
  "reranker": "ovos-bm25-reranker",
  "keyword_extractor": "ovos-rake-keywords"
}
```

### Reranker (`reranker`)

Wikipedia searches often return multiple candidate pages for ambiguous topics — a search for "Mercury" might return the planet, the element, and the god. Without a reranker, results are ordered only by fuzzy title/summary match.

A reranker re-scores all candidate pages against the original query using a cross-encoder model, promoting the most contextually relevant page to the top. This is the single biggest quality improvement for voice use because a wrong page pick means a completely irrelevant spoken answer.

```json
{ "reranker": "ovos-bm25-reranker" }
```

> For better accuracy at the cost of more CPU, use a neural cross-encoder like `ovos-flashrank-reranker-plugin`.

### Extractive QA (`extractive_qa`)

By default the skill speaks the full introductory summary of the best Wikipedia article, which can be several sentences long. An extractive QA plugin reads that summary and extracts the single passage most likely to directly answer the user's question.

**Without extractive QA** — "Tell me about Ada Lovelace":
> *"Ada Lovelace was an English mathematician and writer, chiefly known for her work on Charles Babbage's proposed mechanical general-purpose computer, the Analytical Engine. She was the first to recognise that the machine had applications beyond pure calculation..."*

**With extractive QA** — same query:
> *"Ada Lovelace was the first to recognise that the machine had applications beyond pure calculation."*

Much more natural for a voice interface.

```json
{ "extractive_qa": "ovos-bm25-solver" }
```

> For better precision, use a reading-comprehension model like `ovos-roberta-qa-plugin`.

### Keyword Extractor (`keyword_extractor`)

When the initial Wikipedia search returns no results — common with conversational phrasing like "tell me more about that thing on the moon" — the keyword extractor pulls the most salient terms from the query and retries the search with a cleaner keyword.

Without it, over-specific or colloquial queries silently return nothing. With it, the skill gracefully recovers and finds the right page in most cases.

```json
{ "keyword_extractor": "ovos-rake-keywords" }
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
