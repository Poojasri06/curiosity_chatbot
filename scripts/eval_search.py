"""Measure how well catalogue search finds the right courses.

Usage:  python scripts/eval_search.py [data/courses.json]

Each question lists a pattern that a correct course title must match. A question
"passes" if such a title appears in the top 3 results. Off-topic questions pass if no
course title or category matches (strong_only), so the bot can say "I don't have that".
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.catalogue import Catalogue  # noqa: E402

ON_TOPIC = [
    ("python", r"python"),
    ("I want to learn python programming", r"python"),
    ("python mcq", r"python mcq"),
    ("project management", r"project management"),
    ("cyber security", r"cyber"),
    ("time management", r"time management"),
    ("excel formulas", r"excel formulas"),
    ("excel vba", r"vba"),
    ("react js", r"react"),
    ("machine learning", r"machine learning"),
    ("sql", r"sql"),
    ("leadership", r"leadership"),
    ("teamwork and team building", r"team"),
    ("digital marketing", r"marketing"),
    ("photoshop", r"photoshop"),
    ("power bi", r"power bi"),
    ("interview preparation", r"interview"),
    ("stress management", r"stress"),
    ("javascript", r"javascript"),
    ("html and css", r"html|css"),
    ("electrical wiring", r"wiring"),
    ("communication skills", r"communicat"),
    ("generative AI", r"\bai\b|generative"),
    ("mindfulness", r"mindful"),
    ("java interview questions", r"java"),
]
OFF_TOPIC = [
    "what is the weather today",
    "who won the cricket match",
    "book a flight to Delhi",
    "bitcoin price",
]


def run(catalogue: Catalogue, verbose: bool = True) -> tuple[int, int, int, int]:
    passed = 0
    for question, pattern in ON_TOPIC:
        titles = [h.course.title for h in catalogue.search(question, k=3)]
        ok = any(re.search(pattern, t, re.I) for t in titles)
        passed += ok
        if verbose and not ok:
            print(f"  MISS  {question!r} wanted /{pattern}/ got {titles}")
    off_ok = 0
    for question in OFF_TOPIC:
        titles = [h.course.title for h in catalogue.search(question, k=3, strong_only=True)]
        off_ok += not titles
        if verbose and titles:
            print(f"  NOISE {question!r} returned {titles}")
    return passed, len(ON_TOPIC), off_ok, len(OFF_TOPIC)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/courses.json"
    cat = Catalogue.from_file(path)
    on_ok, on_total, off_ok, off_total = run(cat)
    print(f"On-topic found in top 3: {on_ok}/{on_total}")
    print(f"Off-topic correctly empty: {off_ok}/{off_total}")
