"""A short automatic summary of a lecture transcript, computed locally (no outside service).

Extractive: the transcript is cut into sentences (or into runs of about 25 words when the speech recognition
left no punctuation), each is scored by how many frequent words and glossary terms it holds, and the best ones
are kept in their original order. It shows what the lecturer talked about most; it does not rewrite anything.
"""
from __future__ import annotations

import re
from collections import Counter

from .homework import STOPWORDS, tokens

CHUNK_WORDS = 25
MIN_WORDS = 6


def sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text or "") if p.strip()]
    out: list[str] = []
    for part in parts:
        words = part.split()
        if len(words) <= CHUNK_WORDS * 2:
            out.append(part)
        else:
            out.extend(" ".join(words[i:i + CHUNK_WORDS]) for i in range(0, len(words), CHUNK_WORDS))
    return [s for s in out if len(s.split()) >= MIN_WORDS]


def summarize(text: str, terms: list[str] | None = None, max_sentences: int = 6, max_terms: int = 10) -> dict:
    sents = sentences(text)
    glossary = {t.lower() for t in (terms or [])}
    counts = Counter(w for w in tokens(text) if len(w) >= 4 and not w.isdigit() and w not in STOPWORDS)
    if not sents or not counts:
        return {"sentences": [], "terms": []}

    def score(sentence: str) -> float:
        words = [w for w in tokens(sentence) if len(w) >= 4 and w not in STOPWORDS]
        if not words:
            return 0.0
        value = sum(counts[w] + (3 * counts[w] if w in glossary else 0) for w in set(words))
        return value / (len(words) ** 0.5)

    ranked = sorted(range(len(sents)), key=lambda i: -score(sents[i]))[:min(max_sentences, max(1, len(sents) // 2))]   # never more than half the lecture
    chosen = [sents[i] for i in sorted(ranked)]
    used = [t for t in (terms or []) if t.lower() in counts]
    top = used[:max_terms] if used else [w for w, _ in counts.most_common(max_terms)]
    return {"sentences": chosen, "terms": top}
