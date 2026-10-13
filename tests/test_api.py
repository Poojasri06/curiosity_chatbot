import pytest
from fastapi.testclient import TestClient

from app.catalogue import Catalogue, Course
from app.config import Settings
from app.llm import ProviderError
from app.main import create_app


def course(id, title, category="Programming", about="A course."):
    return Course.from_dict(
        {"id": id, "title": title, "slug": title.lower().replace(" ", "-"), "category": category, "about": about}
    )


CATALOGUE = Catalogue([course(1, "Python for Beginners"), course(2, "Time Management", "Personal Development")])


class Say:
    name = "fake"

    def __init__(self, text):
        self.text = text

    def generate(self, message, context):
        return self.text


class Broken:
    name = "broken"

    def generate(self, message, context):
        raise ProviderError("broken returned HTTP 503")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(Settings(), catalogue=Catalogue([])))


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "echo", "courses": 0}


def test_chat_answers_and_creates_session(client):
    response = client.post("/chat", json={"message": "  Which Python courses do you have?  "})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "(echo) You asked: Which Python courses do you have?"
    assert len(body["session_id"]) == 32
    assert body["sources"] == []
    assert body["mode"] == "ai"


def test_chat_keeps_given_session_id(client):
    response = client.post("/chat", json={"message": "hi", "session_id": "abc123"})
    assert response.json()["session_id"] == "abc123"


@pytest.mark.parametrize("message", ["", "   ", "x" * 1001])
def test_chat_rejects_bad_messages(client, message):
    assert client.post("/chat", json={"message": message}).status_code == 422


def test_chat_requires_message(client):
    assert client.post("/chat", json={}).status_code == 422


def test_unknown_provider_fails_at_startup():
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER 'nope'"):
        create_app(Settings(llm_provider="nope"))


def test_cors_allows_only_listed_origins():
    client = TestClient(create_app(Settings(allowed_origins=["https://lms.example.com"]), catalogue=Catalogue([])))
    allowed = client.get("/health", headers={"Origin": "https://lms.example.com"})
    blocked = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert allowed.headers.get("access-control-allow-origin") == "https://lms.example.com"
    assert "access-control-allow-origin" not in blocked.headers


def test_answer_links_only_courses_it_names():
    app = create_app(Settings(lms_base_url="https://curiosity.live"), CATALOGUE, Say("Try Python for Beginners first."))
    body = TestClient(app).post("/chat", json={"message": "python"}).json()
    assert body["sources"] == [{"title": "Python for Beginners", "url": "https://curiosity.live/courses-details/python-for-beginners"}]
    assert body["mode"] == "ai"


def test_no_links_when_answer_names_no_course():
    app = create_app(Settings(), CATALOGUE, Say("I do not have a matching course."))
    body = TestClient(app).post("/chat", json={"message": "python"}).json()
    assert body["sources"] == []


def test_provider_failure_falls_back_to_search_results():
    app = create_app(Settings(), CATALOGUE, Broken())
    response = TestClient(app).post("/chat", json={"message": "python courses"})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "search"
    assert "Python for Beginners" in body["answer"]
    assert body["sources"][0]["url"] == "/courses-details/python-for-beginners"


def test_provider_failure_without_a_match_still_answers_politely():
    app = create_app(Settings(), CATALOGUE, Broken())
    body = TestClient(app).post("/chat", json={"message": "quantum physics"}).json()
    assert body["mode"] == "search"
    assert body["sources"] == []
    assert "could not find a course" in body["answer"]
    assert "Programming" in body["answer"]
