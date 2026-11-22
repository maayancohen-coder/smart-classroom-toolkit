"""Read the lecture slides (PowerPoint, PDF or plain text) and pull out the English terms.

The terms go into the transcript glossary, and the words of the slides help decide whether a student's
question is about the lecture. PowerPoint files are read with the standard library only (a .pptx is a zip
of XML files); PDF needs the small `pypdf` package.
"""
from __future__ import annotations

import html
import io
import re
import zipfile

MAX_BYTES = 15 * 1024 * 1024
MAX_UNZIPPED = 40 * 1024 * 1024
ENGLISH_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "are", "was", "not", "can", "will", "all",
    "any", "has", "have", "but", "you", "your", "our", "its", "how", "what", "why", "when", "who", "use",
    "used", "using", "new", "one", "two", "page", "slide", "example", "examples", "figure", "see", "also",
}


class SlidesError(Exception):
    pass


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pptx"):
        return _pptx_text(data)
    if name.endswith(".pdf"):
        return _pdf_text(data)
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    raise SlidesError("Supported files: PowerPoint (pptx), PDF or text")


def _pptx_text(data: bytes) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SlidesError("The file is not a valid PowerPoint (pptx) file") from exc
    slides = [i for i in archive.infolist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", i.filename)]
    if sum(i.file_size for i in slides) > MAX_UNZIPPED:
        raise SlidesError("The file is too large")
    slides.sort(key=lambda i: int(re.search(r"(\d+)\.xml", i.filename).group(1)))
    lines = []
    for info in slides:
        xml = archive.read(info).decode("utf-8", errors="replace")
        for paragraph in xml.split("</a:p>"):
            text = "".join(html.unescape(t) for t in re.findall(r"<a:t[^>]*>(.*?)</a:t>", paragraph, re.S))
            if text.strip():
                lines.append(text.strip())
        lines.append("")
    return "\n".join(lines)


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SlidesError("Reading PDF needs the pypdf package. You can upload PowerPoint (pptx) instead.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages[:300])
    except Exception as exc:  # a damaged or protected file
        raise SlidesError("Could not read the PDF") from exc


def extract_terms(text: str, limit: int = 150) -> list[str]:
    """English words and short English phrases (up to 3 words), in order of first appearance."""
    found: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        key = term.lower()
        if key not in seen and len(found) < limit:
            seen.add(key)
            found.append(term)

    for run in re.findall(r"[A-Za-z][A-Za-z0-9+#\-]*(?: [A-Za-z][A-Za-z0-9+#\-]*){0,2}", text):
        words = [w for w in run.split() if w.lower() not in ENGLISH_STOPWORDS]
        if not words:
            continue
        phrase = " ".join(words)
        if len(words) > 1 and len(phrase) >= 5:
            add(phrase)
        for w in words:
            if len(w) >= 4 or (w.isupper() and len(w) >= 2):
                add(w)
    return found


def hebrew_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[֐-׿]{4,}", text)}
