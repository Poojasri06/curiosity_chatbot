import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.catalogue import Catalogue
from app.config import Settings, load_settings
from app.main import create_app

WIDGET = Path(__file__).resolve().parent.parent / "widget" / "widget.js"


def client(**settings):
    return TestClient(create_app(Settings(**settings), catalogue=Catalogue([])))


def test_widget_js_is_served_as_javascript_with_short_cache():
    response = client().get("/widget.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.headers["cache-control"] == "public, max-age=300"
    assert "CuriosityChat" in response.text


def test_demo_page_is_off_by_default_and_on_when_enabled():
    assert client().get("/demo").status_code == 404
    on = client(demo_page=True).get("/demo")
    assert on.status_code == 200 and "/widget.js" in on.text


def test_demo_page_setting_reads_environment(monkeypatch):
    monkeypatch.setenv("DEMO_PAGE", "true")
    assert load_settings().demo_page is True
    monkeypatch.setenv("DEMO_PAGE", "")
    assert load_settings().demo_page is False


def test_widget_never_writes_html_from_text():
    """Answers and course titles come from outside the page, so they may only be added as text."""
    source = WIDGET.read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)  # comments may mention these words
    code = re.sub(r"(?<!:)//[^\n]*", "", code)
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert banned not in code, f"widget.js must not use {banned}"


def test_widget_has_no_external_requests_besides_the_chat_api():
    source = WIDGET.read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    code = re.sub(r"(?<!:)//[^\n]*", "", code)
    assert re.findall(r"https?://[^\s'\"]+", code) == ["http://www.w3.org/2000/svg"]  # the SVG namespace, not a request
    assert code.count("fetch(") == 1
