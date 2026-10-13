"""Course catalogue: loads data/courses.json and ranks courses for a question (BM25 keyword search).

Keyword search needs no model download and runs offline. If the client wants smarter
matching later, embeddings can be added behind the same `search()` method.
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# How much a match in each field counts. A title match matters most.
FIELD_WEIGHTS = {"title": 4, "category": 2, "about": 1, "outcomes": 1}
K1, B = 1.5, 0.75
# A hit must score at least this share of the best hit, so weak matches are dropped.
RELATIVE_CUTOFF = 0.5
# Extra credit when a query word appears in the title or category, and when the
# words appear together, in order, in the title (users usually name the course).
TITLE_BONUS = 1.0  # times the word's rarity
PHRASE_BONUS = 3.0

# Words that say nothing about the topic. All courses here are free, so "free" is noise too.
STOPWORDS = frozenset(
    """a an and any are as at be been but by can could course courses do does for from get give
    have help how i if in into is it its learn like looking me my need of on or our please
    show some suggest tell that the there these this to training tutorial tutorials want we what
    which who will with would you your free beginner beginners good best new topic topics class
    classes available offer offers recommend find tip tips today now basic basics easy simple quick
    start started""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+(?:[+#]+)?")


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in _TOKEN.findall(text.lower()):
        if raw in STOPWORDS:
            continue
        tokens.append(_stem(raw))
    return tokens


def _stem(word: str) -> str:
    """Very light plural stripping so 'courses' and 'course', 'libraries' and 'library' match."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _contains_in_order(tokens: list[str], terms: list[str]) -> bool:
    """True if `terms` appear next to each other, in order, inside `tokens`."""
    n = len(terms)
    return any(tokens[i : i + n] == terms for i in range(len(tokens) - n + 1))


@dataclass(frozen=True)
class Course:
    id: int
    kind: str  # "course" or "quiz"
    title: str
    slug: str
    category: str
    level: str
    price: float
    lessons: int
    certificate: bool
    about: str
    outcomes: str

    @classmethod
    def from_dict(cls, data: dict) -> "Course":
        return cls(
            id=int(data["id"]),
            kind=data.get("kind", "course"),
            title=data["title"],
            slug=data["slug"],
            category=data.get("category", ""),
            level=data.get("level", ""),
            price=float(data.get("price", 0) or 0),
            lessons=int(data.get("lessons", 0) or 0),
            certificate=bool(data.get("certificate", False)),
            about=data.get("about", ""),
            outcomes=data.get("outcomes", ""),
        )

    @property
    def is_free(self) -> bool:
        return self.price == 0


@dataclass(frozen=True)
class Hit:
    course: Course
    score: float
    # True when a query word is in the title or category. Hits that only match words
    # inside the description are weaker and may be off-topic.
    in_title: bool = False


class Catalogue:
    def __init__(self, courses: list[Course]):
        self.courses = courses
        self._tf: list[Counter] = []
        self._length: list[float] = []
        self._title_tokens: list[list[str]] = []
        self._label_tokens: list[set[str]] = []  # title + category words
        df: Counter = Counter()
        for course in courses:
            tf: Counter = Counter()
            for field, weight in FIELD_WEIGHTS.items():
                for token in tokenize(getattr(course, field)):
                    tf[token] += weight
            self._tf.append(tf)
            title_tokens = tokenize(course.title)
            self._title_tokens.append(title_tokens)
            self._label_tokens.append(set(title_tokens) | set(tokenize(course.category)))
            self._length.append(float(sum(tf.values())))
            df.update(tf.keys())
        n = len(courses)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._avg_len = (sum(self._length) / n) if n else 0.0

    @classmethod
    def from_file(cls, path: str | Path | None) -> "Catalogue":
        if not path or not Path(path).is_file():
            log.warning("Course file %s not found; the catalogue is empty.", path)
            return cls([])
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Course.from_dict(item) for item in data])

    def __len__(self) -> int:
        return len(self.courses)

    def search(self, query: str, k: int = 5, kind: str | None = None, strong_only: bool = False) -> list[Hit]:
        """Return up to k best-matching courses for the question, best first.

        strong_only keeps only courses whose title or category matches a query word.
        """
        terms = list(dict.fromkeys(tokenize(query)))  # unique, keep order
        if not terms or not self.courses:
            return []
        scored: list[Hit] = []
        for course, tf, length, title_tokens, labels in zip(
            self.courses, self._tf, self._length, self._title_tokens, self._label_tokens
        ):
            if kind and course.kind != kind:
                continue
            score = 0.0
            in_title = False
            for term in terms:
                freq = tf.get(term)
                if not freq:
                    continue
                idf = self._idf.get(term, 0.0)
                norm = freq + K1 * (1 - B + B * length / self._avg_len)
                score += idf * freq * (K1 + 1) / norm
                if term in labels:
                    score += TITLE_BONUS * idf
                    in_title = True
            if score > 0 and len(terms) > 1 and _contains_in_order(title_tokens, terms):
                score += PHRASE_BONUS
            if score > 0:
                scored.append(Hit(course, score, in_title))
        if strong_only:
            scored = [h for h in scored if h.in_title]
        scored.sort(key=lambda h: (-h.score, h.course.title))
        if not scored:
            return []
        floor = scored[0].score * RELATIVE_CUTOFF
        return [h for h in scored[:k] if h.score >= floor]

    def overview(self, limit: int = 8) -> str:
        """One line describing the whole catalogue, for general questions like 'what do you offer?'."""
        courses = [c for c in self.courses if c.kind == "course"]
        if not courses:
            return ""
        quizzes = len(self.courses) - len(courses)
        free = "free " if all(c.is_free for c in courses) else ""
        biggest = ", ".join(f"{name} ({count})" for name, count in self.categories()[:limit])
        return f"Overview: {len(courses)} {free}courses and {quizzes} quizzes. Biggest categories: {biggest}."

    def categories(self) -> list[tuple[str, int]]:
        """Category names with how many courses each holds, biggest first."""
        counts = Counter(c.category for c in self.courses if c.category and c.kind == "course")
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))
