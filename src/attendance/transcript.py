"""Fix a speech-to-text transcript with the lecturer's glossary of terms.

Speech recognition set to Hebrew writes English technical terms in Hebrew letters ("סטרטגי" for
Strategy). We compare words by how they sound: both the Hebrew word and the English term are reduced to
a short consonant skeleton ("STRTG") and a close match is replaced by the glossary term. No network and
no AI service is needed, so it works in the demo; an LLM can be plugged in later behind the same
function (see TranscriptCorrector in the class diagram).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

HEBREW_CLASSES = {
    "ב": "B", "ג": "G", "ד": "D", "ז": "Z", "ח": "K", "ט": "T", "ת": "T", "כ": "K", "ך": "K", "ק": "K",
    "ל": "L", "מ": "M", "ם": "M", "נ": "N", "ן": "N", "ס": "S", "ש": "S", "צ": "S", "פ": "P", "ף": "P", "ר": "R",
}                                   # א ה ו י ע are vowel letters here: dropped
PREFIXES = "בהולמשכו"                # one-letter Hebrew prefixes glued to a word
LETTER_NAMES = {                    # how a spoken acronym comes out in Hebrew letters
    "A": "איי", "B": "בי", "C": "סי", "D": "די", "E": "אי", "F": "אף", "G": "גי", "H": "אייץ",
    "I": "איי", "J": "גיי", "K": "קיי", "L": "אל", "M": "אם", "N": "אן", "O": "או", "P": "פי",
    "Q": "קיו", "R": "אר", "S": "אס", "T": "טי", "U": "יו", "V": "וי", "W": "דאבליו", "X": "אקס",
    "Y": "וואי", "Z": "זד",
}
NAME_TO_LETTER = {v: k for k, v in LETTER_NAMES.items()}
NAME_TO_LETTER.update({"גיי": "J", "ג'י": "G", "ג'יי": "J", "אייץ'": "H", "יו": "U"})
MAX_WINDOW = 4
MIN_RATIO = 0.78


def _collapse(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def hebrew_skeleton(word: str) -> str:
    return _collapse("".join(HEBREW_CLASSES.get(c, "") for c in word))


def latin_skeletons(term: str) -> set[str]:
    """Possible sounds of an English term as a skeleton; 'c' can sound like k or s."""
    out = set()
    for soft_c in ("K", "S"):
        t, res, i = term.lower(), "", 0
        while i < len(t):
            two, c = t[i:i + 2], t[i]
            if two in ("sh", "ch", "ph", "th", "ck", "ts"):
                res += {"sh": "S", "ch": "K", "ph": "P", "th": "T", "ck": "K", "ts": "S"}[two]; i += 2; continue
            res += {"b": "B", "c": soft_c, "d": "D", "f": "P", "g": "G", "j": "G", "k": "K", "l": "L", "m": "M",
                    "n": "N", "p": "P", "q": "K", "r": "R", "s": "S", "t": "T", "v": "B", "x": "KS", "z": "Z"}.get(c, "")
            i += 1
        out.add(_collapse(res))
    return {s for s in out if s}


def _similar(heard: str, wanted: set[str]) -> float:
    if not heard:
        return 0.0
    best = 0.0
    for w in wanted:
        if len(w) <= 3 or len(heard) <= 3:
            ratio = 1.0 if w == heard and len(w) >= 3 else 0.0   # short skeletons must match exactly
        elif abs(len(heard) - len(w)) > max(1, 0.3 * len(w)):
            ratio = 0.0                                              # far too long or too short to be this term
        else:
            ratio = SequenceMatcher(None, heard, w).ratio()
        best = max(best, ratio)
    return best


def _split_token(tok: str):
    m = re.match(r"^([^\w֐-׿]*)(.*?)([^\w֐-׿]*)$", tok, re.S)
    return m.group(1), m.group(2), m.group(3)


def _strip_prefix(core: str):
    """'בסטרטגי' -> ('ב', 'סטרטגי'); 'ב-Interface' -> ('ב-', 'Interface')."""
    m = re.match(r"^([" + PREFIXES + r"])[-־](.+)$", core)
    if m:
        return m.group(1) + "-", m.group(2)
    return "", core


@dataclass
class Fix:
    heard: str
    term: str


@dataclass
class Correction:
    text: str
    fixes: list[Fix] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)   # glossary terms that never appear in the result


def parse_glossary(raw: str) -> list[str]:
    terms = [t.strip() for t in re.split(r"[\n,;]+", raw or "") if t.strip()]
    seen, out = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:200]


def correct_transcript(raw: str, glossary: list[str]) -> Correction:
    tokens = re.findall(r"\S+", raw or "")
    parts = [_split_token(t) for t in tokens]
    terms = sorted(glossary, key=lambda t: -len(t.split()))
    skeletons = {t: latin_skeletons(t.replace(" ", "")) for t in terms}
    out, fixes, i = [], [], 0
    while i < len(tokens):
        best = None   # (score, size, term, prefix)
        for term in terms:
            for size in range(1, min(MAX_WINDOW, len(tokens) - i) + 1):
                window = parts[i:i + size]
                prefix, first = _strip_prefix(window[0][1])
                cores = [first] + [p[1] for p in window[1:]]
                heard_text = " ".join(cores)
                score = 0.0
                if re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", heard_text):          # already English
                    score = 1.0 if heard_text.lower().replace("-", " ") == term.lower() else 0.0
                elif term.isupper() and 2 <= len(term) <= 5 and size == len(term):  # spoken acronym
                    letters = "".join(NAME_TO_LETTER.get(re.sub(r"['׳]", "", c) if c not in NAME_TO_LETTER else c, "?")
                                      for c in cores)
                    score = 1.0 if letters == term else 0.0
                elif all(re.search(r"[֐-׿]", c) for c in cores):
                    score = _similar(hebrew_skeleton("".join(cores)), skeletons[term])
                    if prefix == "" and len(cores[0]) > 3 and cores[0][0] in PREFIXES:
                        # a glued prefix without a hyphen: use it when it fits at least as well
                        stripped = _similar(hebrew_skeleton(cores[0][1:] + "".join(cores[1:])), skeletons[term])
                        if stripped >= MIN_RATIO and stripped >= score:
                            score, prefix = stripped, cores[0][0]
                if score >= MIN_RATIO and (best is None or (score, -size) > (best[0], -best[1])):
                    best = (score, size, term, prefix)
        if best is None:
            out.append(tokens[i]); i += 1; continue
        score, size, term, prefix = best
        window = parts[i:i + size]
        heard = " ".join(p[1] for p in window)
        glue = prefix if prefix.endswith("-") or prefix == "" else prefix + "-"
        replacement = window[0][0] + glue + term + window[-1][2]
        if replacement != " ".join(tokens[i:i + size]):
            fixes.append(Fix(heard, term))
        out.append(replacement)
        i += size
    text = " ".join(out)
    missing = [t for t in glossary if t.lower() not in text.lower()]
    return Correction(text, fixes, missing)
