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
NAME_TO_LETTER["איי"] = "AI"          # the same sound for A and I
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


def _score(parts: list, i: int, size: int, term: str, skeletons: dict):
    """How well tokens i..i+size-1 match the glossary term; returns (score, hebrew_prefix)."""
    window = parts[i:i + size]
    if len(window) < size:
        return 0.0, ""
    prefix, first = _strip_prefix(window[0][1])
    cores = [first] + [p[1] for p in window[1:]]
    heard_text = " ".join(cores)
    if re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", heard_text):                       # already English
        return (1.0 if heard_text.lower().replace("-", " ") == term.lower() else 0.0), prefix
    if term.isupper() and 2 <= len(term) <= 5:                                    # spoken acronym
        if size != len(term):
            return 0.0, ""
        options = [NAME_TO_LETTER.get(c.replace("'", "").replace("\u05F3", ""), "?") for c in cores]
        return (1.0 if all(term[k] in options[k] for k in range(len(term))) else 0.0), prefix
    if all(re.search(r"[\u0590-\u05FF]", c) for c in cores):
        score = _similar(hebrew_skeleton("".join(cores)), skeletons[term])
        if prefix == "" and len(cores[0]) > 3 and cores[0][0] in PREFIXES:
            # a glued prefix without a hyphen: use it when it fits at least as well
            stripped = _similar(hebrew_skeleton(cores[0][1:] + "".join(cores[1:])), skeletons[term])
            if stripped >= MIN_RATIO and stripped >= score:
                return stripped, cores[0][0]
        return score, prefix
    return 0.0, ""


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
                score, prefix = _score(parts, i, size, term, skeletons)
                if score < MIN_RATIO:
                    continue
                # A longer window must not just carry an extra word: if dropping the first or the
                # last token matches as well, the shorter window is the real match.
                if size > 1 and (_score(parts, i + 1, size - 1, term, skeletons)[0] >= score - 0.001
                                 or _score(parts, i, size - 1, term, skeletons)[0] >= score - 0.001):
                    continue
                if best is None or (score, -size) > (best[0], -best[1]):
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


# ---------------------------------------------------------------------------------------------
# Only the lecturer's voice: a quiet voice is a student. A student's question is kept only when it is
# a relevant question that the lecturer answers.
QUESTION_WORDS = {"מה", "איך", "למה", "האם", "מתי", "איפה", "מי", "כמה", "מדוע", "איזה", "אילו", "אז", "שאלה"}
STOPWORDS = {"אבל", "כמו", "אפשר", "צריך", "זאת", "הזה", "הזאת", "שלנו", "היום", "עוד", "גם", "אולי", "יכול", "יכולה", "אתה"}
ANSWER_WITHIN_SECONDS = 20.0


@dataclass
class Segment:
    text: str
    level: float      # how loud the voice was at the microphone (0 to 1)
    t0: float
    t1: float


@dataclass
class Assembled:
    text: str
    questions: int = 0
    dropped: list[dict] = field(default_factory=list)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[\w\u0590-\u05FF]{4,}", text.lower()) if w not in STOPWORDS}


def _looks_like_question(text: str) -> bool:
    first = re.findall(r"[\w\u0590-\u05FF]+", text)[:2]
    return text.strip().endswith("?") or any(w.lstrip("והשלב") in QUESTION_WORDS or w in QUESTION_WORDS for w in first)


def assemble_lecturer_transcript(segments: list[Segment], threshold: float, terms: list[str],
                                 context_words: frozenset | set = frozenset()) -> Assembled:
    lines, dropped, questions = [], [], 0
    lowered_terms = [t.lower() for t in terms]
    for i, seg in enumerate(segments):
        if seg.level >= threshold:
            lines.append(seg.text)
            continue
        answer = next((s for s in segments[i + 1:] if s.level >= threshold and s.t1 - seg.t1 <= ANSWER_WITHIN_SECONDS), None)
        if not _looks_like_question(seg.text):
            dropped.append({"text": seg.text, "reason": "quiet voice, not a question"})
        elif answer is None:
            dropped.append({"text": seg.text, "reason": "question that the lecturer did not answer"})
        elif not (_words(seg.text) & _words(answer.text) or any(t in seg.text.lower() for t in lowered_terms)
                  or _words(seg.text) & set(context_words)):
            dropped.append({"text": seg.text, "reason": "question not related to the lecturer's answer"})
        else:
            lines.append("[שאלה מהכיתה] " + seg.text)
            questions += 1
    return Assembled(" ".join(lines), questions, dropped)
