import sys
from pathlib import Path

import pytest

from app.catalogue import Catalogue, Course

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def make(id, title, category="Programming", about="", kind="course", outcomes=""):
    return Course.from_dict(
        {"id": id, "kind": kind, "title": title, "slug": title.lower().replace(" ", "-"),
         "category": category, "about": about, "outcomes": outcomes}
    )


@pytest.fixture()
def catalogue():
    return Catalogue(
        [
            make(1, "Python for Beginners", about="Learn variables, loops and functions."),
            make(2, "Advanced Python Programming", about="Decorators and generators."),
            make(3, "Time Management", "Personal Development", "Plan your day and avoid distractions."),
            make(4, "Excel Formulas", "Office Productivity", "Use the match function and lookups."),
            make(5, "Python MCQ", "", kind="quiz"),
        ]
    )


def titles(hits):
    return [h.course.title for h in hits]


def test_title_match_ranks_first(catalogue):
    assert titles(catalogue.search("time management"))[0] == "Time Management"


def test_plural_and_filler_words_are_ignored(catalogue):
    hits = catalogue.search("Which python courses do you have?")
    assert set(titles(hits)) >= {"Python for Beginners", "Advanced Python Programming"}


def test_unknown_topic_returns_nothing(catalogue):
    assert catalogue.search("quantum cryptography") == []


def test_empty_or_filler_only_question_returns_nothing(catalogue):
    assert catalogue.search("") == []
    assert catalogue.search("what do you have please") == []


def test_description_only_match_is_not_strong(catalogue):
    hits = catalogue.search("cricket match")
    assert titles(hits) == ["Excel Formulas"]  # matches the word "match" in the description
    assert hits[0].in_title is False
    assert catalogue.search("cricket match", strong_only=True) == []


def test_kind_filter(catalogue):
    assert titles(catalogue.search("python", kind="quiz")) == ["Python MCQ"]


def test_k_limits_results(catalogue):
    assert len(catalogue.search("python", k=1)) == 1


def test_categories_count_courses_only(catalogue):
    assert dict(catalogue.categories()) == {"Programming": 2, "Personal Development": 1, "Office Productivity": 1}


def test_missing_file_gives_empty_catalogue(tmp_path):
    empty = Catalogue.from_file(tmp_path / "nope.json")
    assert len(empty) == 0
    assert empty.search("python") == []


@pytest.mark.skipif(not (ROOT / "data" / "courses.json").exists(), reason="no exported course data")
def test_real_catalogue_quality():
    import eval_search

    on_ok, on_total, off_ok, off_total = eval_search.run(
        Catalogue.from_file(ROOT / "data" / "courses.json"), verbose=False
    )
    assert on_ok / on_total >= 0.9
    assert off_ok == off_total
