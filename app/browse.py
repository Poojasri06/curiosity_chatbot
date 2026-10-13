"""Browse the catalogue by department, without the AI model.

Visitors who say "list all courses" are asked to pick a department, then see that department's courses
a page at a time. The catalogue has near-duplicate category names (for example "Marketing" and
"Digital Marketing", or a misspelt "Artificial Intelligents"); ALIASES merges them for display.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .catalogue import Catalogue, Course, tokenize
from .schemas import Choice

PAGE_SIZE = 8

ALIASES = {
    "artificial intelligents": "Artificial Intelligence",
    "digital marketing": "Marketing",
    "development": "Programming",
    "microsoft": "Office Productivity",
    "photography & video": "Design",
    "electrical & electronics engineering": "Engineering",
    "mechanical engineering": "Engineering",
    "electronics": "Engineering",
}

# Words visitors type for a department, mapped to the department's name.
SYNONYMS = {
    "development": "Programming",
    "developer": "Programming",
    "coding": "Programming",
    "software": "IT & Software",
    "it": "IT & Software",
    "ai": "Artificial Intelligence",
    "tech": "Technology",
    "hr": "HR",
    "management": "Business",
    "productivity": "Office Productivity",
}

LIST_WORDS = {"list", "show", "browse", "see", "display", "view", "give", "tell", "all", "every", "entire", "whole"}
COURSE_WORDS = {"course", "courses", "categories", "category", "department", "departments", "catalogue", "catalog"}
FILLER = {
    "me", "the", "of", "you", "have", "can", "i", "please", "available", "what", "do", "are", "there", "your", "any",
    "a", "an", "to", "in", "by", "and", "offer", "provide", "is", "we", "us", "for", "my", "want", "would", "like",
    "could", "on", "platform", "here", "which", "with", "from", "choose", "select", "pick", "options", "option",
    "department", "departments", "category", "categories", "course", "courses", "catalogue", "catalog",
}


@dataclass
class Department:
    name: str
    courses: list[Course]


class Browser:
    def __init__(self, catalogue: Catalogue):
        groups: dict[str, list[Course]] = {}
        for course in catalogue.courses:
            if course.kind != "course" or not course.category:
                continue
            name = ALIASES.get(course.category.strip().lower(), course.category.strip())
            groups.setdefault(name, []).append(course)
        ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))
        self.departments = [Department(name, sorted(courses, key=lambda c: re.sub(r"^\W+", "", c.title.lower()))) for name, courses in ordered]
        self._by_name = {d.name.lower(): d for d in self.departments}
        self._token_index: dict[str, Department] = {}
        for d in self.departments:
            for token in tokenize(d.name):
                self._token_index.setdefault(token, d)

    def find(self, name: str) -> Department | None:
        key = (name or "").strip().lower()
        return self._by_name.get(ALIASES.get(key, key).lower())

    def wants_browsing(self, message: str) -> tuple[bool, Department | None]:
        """Does the message ask to list courses by department? If it names one, also returns it.

        Messages about a topic ("list python courses") are not browsing: they fall through to search.
        """
        words = re.findall(r"[a-z0-9&']+", message.lower())
        if not words:
            return False, None
        has_course_word = any(w in COURSE_WORDS for w in words)
        has_list_word = any(w in LIST_WORDS for w in words)
        asks = (has_list_word and has_course_word) or any(w in {"categories", "departments", "catalogue", "catalog"} for w in words)
        asks = asks or bool(re.search(r"\bwhat (courses|categories|departments)\b", message.lower()))
        if not asks:
            return False, None
        rest = [w for w in words if w not in LIST_WORDS and w not in FILLER and w not in COURSE_WORDS]
        if not rest:
            return True, None
        department = self._match_department(rest)
        return (True, department) if department else (False, None)

    def _match_department(self, words: list[str]) -> Department | None:
        text = " ".join(words)
        for d in self.departments:
            if d.name.lower() in text:
                return d
        found = [self._lookup(w) for w in words]
        if found and all(d is not None for d in found) and len({d.name for d in found}) == 1:
            return found[0]
        return None

    def _lookup(self, word: str) -> Department | None:
        if word in SYNONYMS:
            return self.find(SYNONYMS[word])
        tokens = tokenize(word)
        return self._token_index.get(tokens[0]) if tokens else None

    # -- replies ---------------------------------------------------------------------------

    def choose_department(self) -> tuple[str, list[Choice]]:
        text = "I would be glad to show you. Which department are you interested in?"
        choices = [Choice(label=f"{d.name} ({len(d.courses)})", category=d.name) for d in self.departments]
        return text, choices

    def page(self, department: Department, offset: int = 0) -> tuple[str, list[Course], list[Choice]]:
        total = len(department.courses)
        offset = min(max(offset, 0), max(total - 1, 0))
        shown = department.courses[offset : offset + PAGE_SIZE]
        end = offset + len(shown)
        noun = "course" if total == 1 else "courses"
        if total <= PAGE_SIZE:
            text = f"{department.name} has {total} {noun}. Tap any title to open it."
        else:
            text = f"Here are {department.name} courses {offset + 1} to {end} of {total}. Tap any title to open it."
        choices = []
        if end < total:
            remaining = min(PAGE_SIZE, total - end)
            choices.append(Choice(label=f"Show {remaining} more", category=department.name, offset=end))
        choices.append(Choice(label="Other departments", category="*"))
        return text, shown, choices
