"""Turns a question into an answer: search the catalogue, ask the AI model, add links.

If the AI provider fails (rate limit, outage, missing key), the user still gets a useful
list of matching courses instead of an error.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .browse import Browser
from .catalogue import Catalogue, Course, Hit
from .config import Settings
from .llm import LLMProvider, ProviderError
from .help import find_topic, help_answer
from .schemas import Choice, Source

log = logging.getLogger(__name__)

CONTEXT_COURSES = 5  # courses shown to the AI model
SOURCE_LIMIT = 3  # links shown under an answer
SUMMARY_CHARS = 220


def plain_text(text: str) -> str:
    """Removes markdown symbols the model may still add (asterisks, headings, backticks)."""
    text = re.sub(r"^[ \t]*[*•][ \t]+", "- ", text, flags=re.M)  # bullet asterisks become dashes
    text = re.sub(r"^[ \t]*#{1,6}[ \t]*", "", text, flags=re.M)
    text = re.sub(r"[*_`]{1,3}(\S(?:.*?\S)?)[*_`]{1,3}", r"\1", text)  # **bold**, *italic*, `code`
    text = text.replace("*", "").replace("`", "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


@dataclass
class Answer:
    text: str
    sources: list[Source] = field(default_factory=list)
    mode: str = "ai"
    choices: list[Choice] = field(default_factory=list)


class Answerer:
    def __init__(self, catalogue: Catalogue, provider: LLMProvider, settings: Settings):
        self._catalogue = catalogue
        self._provider = provider
        self._settings = settings
        self._browser = Browser(catalogue)

    def answer(self, question: str, category: str | None = None, offset: int = 0) -> Answer:
        # Department buttons, website help and "list all courses" are answered without the AI model.
        if category:
            return self._departments() if category == "*" else self._department(category, offset)
        topic = find_topic(question)
        if topic:
            text, sources = help_answer(topic, self._settings.lms_base_url)
            return Answer(text, sources, mode="help")
        wants, department = self._browser.wants_browsing(question)
        if wants:
            return self._department(department.name, 0) if department else self._departments()
        hits = self._catalogue.search(question, k=CONTEXT_COURSES)
        context = self._context(hits)
        try:
            text = self._provider.generate(question, context)
        except ProviderError as exc:
            log.warning("AI provider failed (%s); answering from search results.", exc)
            return self._fallback(hits)
        text = plain_text(text)
        return Answer(text=text, sources=self._sources_named_in(text, hits))

    # -- browsing by department --------------------------------------------------------

    def _departments(self) -> Answer:
        text, choices = self._browser.choose_department()
        return Answer(text, mode="browse", choices=choices)

    def _department(self, name: str, offset: int) -> Answer:
        department = self._browser.find(name)
        if department is None:
            return self._departments()
        text, courses, choices = self._browser.page(department, offset)
        return Answer(text, [self._source(c) for c in courses], mode="browse", choices=choices)

    # -- helpers ---------------------------------------------------------------

    def _context(self, hits: list[Hit]) -> list[str]:
        lines = []
        overview = self._catalogue.overview()
        if overview:
            lines.append(overview)
        for hit in hits:
            c = hit.course
            facts = [c.category, f"{c.lessons} lessons" if c.lessons else "", "free" if c.is_free else f"price {c.price:g}"]
            facts_text = "; ".join(f for f in facts if f)
            kind = "Quiz" if c.kind == "quiz" else "Course"
            summary = c.about[:SUMMARY_CHARS].rstrip()
            lines.append(f"- {kind}: {c.title} ({facts_text}). {summary}")
        return lines

    def _url(self, course: Course) -> str:
        path = self._settings.quiz_path if course.kind == "quiz" else self._settings.course_path
        return self._settings.lms_base_url + path.format(slug=course.slug)

    def _source(self, course: Course) -> Source:
        return Source(title=course.title, url=self._url(course))

    def _sources_named_in(self, text: str, hits: list[Hit]) -> list[Source]:
        """Link only the courses the answer actually names, so links never contradict the text."""
        lowered = text.lower()
        named = [h.course for h in hits if h.course.title.lower() in lowered]
        return [self._source(c) for c in named[:SOURCE_LIMIT]]

    def _fallback(self, hits: list[Hit]) -> Answer:
        strong = [h.course for h in hits if h.in_title][:SOURCE_LIMIT]
        if strong:
            lines = [f"- {c.title} ({c.category})" if c.category else f"- {c.title}" for c in strong]
            text = "Here are courses that match your question:\n" + "\n".join(lines)
            return Answer(text, [self._source(c) for c in strong], mode="search")
        topics = ", ".join(name for name, _ in self._catalogue.categories()[:3])
        text = "I could not find a course matching that."
        if topics:
            text += f" Try a topic such as {topics}."
        return Answer(text, [], mode="search")
