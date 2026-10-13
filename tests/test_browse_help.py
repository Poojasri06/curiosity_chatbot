from fastapi.testclient import TestClient

from app.browse import PAGE_SIZE, Browser
from app.catalogue import Catalogue, Course
from app.config import Settings
from app.help import find_topic
from app.main import create_app


def course(i, title, category, kind="course"):
    return Course.from_dict({"id": i, "kind": kind, "title": title, "slug": f"c{i}", "category": category, "about": title})


def catalogue():
    rows = [course(i, f"Prog {i:02d}", "Programming") for i in range(PAGE_SIZE + 4)]
    rows += [course(100, "SEO", "Digital Marketing"), course(101, "Ads", "Marketing"), course(102, "ML", "Artificial Intelligents")]
    rows += [course(103, "Quiz", "", kind="quiz"), course(104, "HR 1", "HR")]
    return Catalogue(rows)


def test_similar_categories_are_merged_and_quizzes_left_out():
    names = {d.name: len(d.courses) for d in Browser(catalogue()).departments}
    assert names == {"Programming": PAGE_SIZE + 4, "Marketing": 2, "Artificial Intelligence": 1, "HR": 1}


def test_which_messages_mean_browsing():
    b = Browser(catalogue())
    for text in ["list me the course", "list me all the courses you have", "Browse courses by department", "what categories do you have"]:
        assert b.wants_browsing(text) == (True, None), text
    assert b.wants_browsing("list all marketing courses")[1].name == "Marketing"
    assert b.wants_browsing("show development courses")[1].name == "Programming"
    for text in ["list python courses", "I want to learn ai", "hello", "python courses"]:
        assert b.wants_browsing(text)[0] is False, text


def test_pages_have_show_more_and_other_departments():
    b = Browser(catalogue())
    prog = b.find("Programming")
    text, shown, choices = b.page(prog, 0)
    assert len(shown) == PAGE_SIZE and "1 to 8 of 12" in text
    assert [c.label for c in choices] == ["Show 4 more", "Other departments"] and choices[0].offset == PAGE_SIZE
    text, shown, choices = b.page(prog, PAGE_SIZE)
    assert len(shown) == 4 and [c.label for c in choices] == ["Other departments"]
    assert b.find("digital marketing").name == "Marketing"  # old names still resolve


def client(**kw):
    return TestClient(create_app(Settings(lms_base_url="https://curiosity.live", **kw), catalogue()))


def test_chat_asks_for_department_then_lists_without_the_ai():
    c = client()  # echo provider: would answer "(echo) ..." if the AI were used
    first = c.post("/chat", json={"message": "list all courses"}).json()
    assert first["mode"] == "browse" and "department" in first["answer"]
    assert {ch["category"] for ch in first["choices"]} >= {"Programming", "Marketing"}
    page = c.post("/chat", json={"message": "Programming", "category": "Programming", "offset": 0}).json()
    assert len(page["sources"]) == PAGE_SIZE and page["sources"][0]["url"] == "https://curiosity.live/courses-details/c0"
    more = c.post("/chat", json={"message": "more", "category": "Programming", "offset": PAGE_SIZE}).json()
    assert len(more["sources"]) == 4
    back = c.post("/chat", json={"message": "Other departments", "category": "*"}).json()
    assert back["choices"] and back["mode"] == "browse"
    unknown = c.post("/chat", json={"message": "x", "category": "Nonsense"}).json()
    assert unknown["choices"]  # falls back to the department list


def test_bad_offset_is_rejected():
    assert client().post("/chat", json={"message": "x", "category": "HR", "offset": -1}).status_code == 422


def test_help_topics_and_links():
    cases = {
        "where can I create my account?": ("/register", "create_account"),
        "how do i sign up": ("/register", "create_account"),
        "i forgot my password": ("/login", "forgot_password"),
        "where do i log in": ("/login", "login"),
        "how can I contact support": ("/contact-us", "contact"),
        "how to become an instructor": ("/become-instructor", "become_instructor"),
    }
    c = client()
    for text, (path, name) in cases.items():
        assert find_topic(text).name == name, text
        body = c.post("/chat", json={"message": text}).json()
        assert body["mode"] == "help" and body["sources"][0]["url"] == "https://curiosity.live" + path, text


def test_course_questions_are_not_taken_for_help():
    for text in ["I want to learn python", "register for the python course", "marketing basics"]:
        assert find_topic(text) is None, text
