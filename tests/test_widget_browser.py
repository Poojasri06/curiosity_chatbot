"""Drives the real widget in Chromium against a live copy of the service.

Needs:  pip install playwright && playwright install chromium   (skipped if not available)
"""
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, urlparse

import pytest

from app.catalogue import Catalogue, Course
from app.config import Settings
from app.main import create_app

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")
expect = sync_api.expect

def course(id, title, category):
    return Course.from_dict(
        {"id": id, "title": title, "slug": title.lower().replace(" ", "-"), "category": category, "about": f"About {title}."}
    )


CATALOGUE = Catalogue(
    [
        course(1, "Python for Beginners", "Programming"),
        course(2, "Servant Leadership", "Business"),
        course(3, "Excel Formulas", "Office Productivity"),
    ]
)


class Guide:
    """Names the first course it is given, like a grounded model would."""

    name = "guide"

    def generate(self, message, context):
        for line in context:
            match = re.match(r"- (?:Course|Quiz): (.+?) \(", line)
            if match:
                return f"You could start with {match.group(1)}."
        return "I do not have a matching course."


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class SiteStub(BaseHTTPRequestHandler):
    """A tiny stand-in for a website that has the widget script tag on it.

    The script tag's extra attributes come from ?attrs=... so each test can choose its own.
    """

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/serviceworker.js":
            # Mirrors the LMS worker: it answers every GET itself through fetch().
            body = (
                b"self.addEventListener('install',e=>self.skipWaiting());"
                b"self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));"
                b"self.addEventListener('fetch',e=>{if(e.request.method==='GET')e.respondWith(fetch(e.request));});"
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        attrs = query.get("attrs", [""])[0]
        csp = query.get("csp", [""])[0].replace("{api}", self.server.api)
        sw = "<script>navigator.serviceWorker.register('/serviceworker.js')</script>" if query.get("sw") else ""
        html = (
            f'<!doctype html><title>Site</title><body><p>A page on another website</p>{sw}'
            f'<script src="{self.server.api}/widget.js" {attrs} defer></script></body>'
        )
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if csp:
            self.send_header("Content-Security-Policy", csp)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep test output quiet
        pass


@pytest.fixture(scope="module")
def stack():
    """The API plus two other websites on different ports (so calls between them are cross-origin).

    `lms` is on the API's allow-list, like curiosity.live would be; `other` is not.
    """
    api_port, lms_port, other_port = free_port(), free_port(), free_port()
    api, lms, other = (f"http://127.0.0.1:{p}" for p in (api_port, lms_port, other_port))
    app = create_app(
        Settings(demo_page=True, allowed_origins=[lms], rate_per_minute=0, rate_per_day=0, rate_global_per_day=0),
        CATALOGUE,
        Guide(),
    )  # rate limits off: these tests send many questions from one address
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=api_port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    sites = []
    for port in (lms_port, other_port):
        site = ThreadingHTTPServer(("127.0.0.1", port), SiteStub)
        site.api = api
        threading.Thread(target=site.serve_forever, daemon=True).start()
        sites.append(site)
    deadline = time.time() + 10
    while not uv.started and time.time() < deadline:
        time.sleep(0.05)
    assert uv.started, "test server did not start"
    yield SimpleNamespace(api=api, lms=lms, other=other)
    uv.should_exit = True
    for site in sites:
        site.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def server(stack):
    return stack.api


def with_attrs(site, attrs="", extra=""):
    return f"{site}/?attrs={quote(attrs, safe='')}{extra}"


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            instance = p.chromium.launch()
        except Exception:
            try:
                instance = p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
            except Exception as exc:  # no browser installed here
                pytest.skip(f"Chromium not available: {exc}")
        yield instance
        instance.close()


@pytest.fixture()
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.set_default_timeout(5000)
    page.js_errors = []
    page.on("pageerror", lambda error: page.js_errors.append(str(error)))
    yield page
    context.close()


def launcher(page):
    return page.get_by_role("button", name="Ask Curi-Assist")


def dialog(page, name="Curi-Assist"):
    return page.get_by_role("dialog", name=name)


def box(page):
    return page.get_by_role("textbox", name="Your message")


def open_demo(page, server):
    page.goto(server + "/demo")
    launcher(page).click()
    expect(dialog(page)).to_be_visible()


def ask(page, text):
    box(page).fill(text)
    box(page).press("Enter")


# ---- the basics ------------------------------------------------------------------------


def test_opens_with_greeting_and_starter_questions(page, server):
    page.goto(server + "/demo")
    expect(launcher(page)).to_be_visible()
    expect(dialog(page)).to_be_hidden()
    launcher(page).click()
    expect(dialog(page)).to_be_visible()
    expect(page.get_by_text("Hello and welcome to Curiosity")).to_be_visible()
    for chip in ["Browse courses by department", "Python courses", "How do I create an account?", "What can I learn here?"]:
        expect(page.get_by_role("button", name=chip)).to_be_visible()
    expect(box(page)).to_be_focused()
    assert page.js_errors == []


def test_starter_question_gets_answer_with_course_link(page, server):
    open_demo(page, server)
    page.get_by_role("button", name="Python courses").click()
    expect(page.get_by_text("You could start with Python for Beginners.")).to_be_visible()
    link = page.get_by_role("link", name=re.compile("Python for Beginners"))
    expect(link).to_have_attribute("href", re.compile(r"/courses-details/python-for-beginners$"))
    expect(link).to_have_attribute("target", "_blank")
    assert "noopener" in link.get_attribute("rel")
    expect(page.get_by_role("button", name="Python courses")).to_have_count(0)  # starters go away after use
    assert page.js_errors == []


def test_enter_sends_shift_enter_adds_a_line_and_empty_is_ignored(page, server):
    open_demo(page, server)
    requests = []
    page.on("request", lambda r: requests.append(r) if r.url.endswith("/chat") else None)
    box(page).press("Enter")
    box(page).fill("   ")
    box(page).press("Enter")
    box(page).fill("python")
    box(page).press("Shift+Enter")
    box(page).type("please")
    assert box(page).input_value() == "python\nplease"
    assert requests == []
    box(page).press("Enter")
    expect(page.get_by_text("You could start with Python for Beginners.")).to_be_visible()
    assert len(requests) == 1
    assert page.locator(".turn.user .msg p").all_inner_texts() == ["python", "please"]  # line break kept


def test_second_message_is_blocked_while_waiting_and_send_is_disabled(page, server):
    open_demo(page, server)
    held, sent, gate = [], [], {"hold": True}

    def handler(route):
        if gate["hold"]:
            held.append(route)  # keep the first request waiting, like a slow AI provider
        else:
            route.continue_()

    page.route("**/chat", handler)
    page.on("request", lambda r: sent.append(r) if r.url.endswith("/chat") else None)
    ask(page, "python")
    expect(page.get_by_role("button", name="Send message")).to_be_disabled()
    box(page).fill("excel")
    box(page).press("Enter")
    page.wait_for_timeout(200)
    assert len(sent) == 1
    gate["hold"] = False
    held[0].continue_()
    expect(page.get_by_text("You could start with Python for Beginners.")).to_be_visible()
    expect(page.get_by_role("button", name="Send message")).to_be_enabled()


# ---- isolation and safety -----------------------------------------------------------------


def test_page_styles_cannot_restyle_the_widget(page, server):
    page.goto(server + "/demo")
    # Sanity check that the demo page really is hostile to ordinary elements.
    assert page.locator("p.page-note").evaluate("e => getComputedStyle(e).borderTopStyle") == "dashed"
    style = page.locator(".launcher").evaluate(
        "e => { const s = getComputedStyle(e); return {font: s.fontFamily, border: s.borderTopStyle, bg: s.backgroundColor, margin: s.marginTop}; }"
    )
    assert "Comic" not in style["font"]
    assert style["border"] == "none" and style["margin"] == "0px"
    assert style["bg"] == "rgb(13, 110, 253)"


def test_answer_text_is_never_run_as_html_and_unsafe_links_are_dropped(page, server):
    open_demo(page, server)
    evil = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=2</script>'
    page.route(
        "**/chat",
        lambda route: route.fulfill(
            json={
                "answer": evil + "\n- first point\n- second point",
                "session_id": "s1",
                "mode": "ai",
                "sources": [
                    {"title": "Bad link", "url": "javascript:window.__pwned=3"},
                    {"title": "Data link", "url": "data:text/html,<script>1</script>"},
                    {"title": "Good <b>course</b>", "url": "https://curiosity.live/courses-details/good"},
                ],
            }
        ),
    )
    ask(page, "hello")
    expect(page.get_by_text("first point")).to_be_visible()
    assert page.evaluate("window.__pwned") is None
    expect(page.get_by_text('<img src=x onerror="window.__pwned=1">', exact=False)).to_be_visible()
    expect(page.locator(".msg img")).to_have_count(0)
    expect(page.locator("li", has_text="first point")).to_be_visible()  # bullets become a real list
    links = page.locator("a.course")
    expect(links).to_have_count(1)
    expect(links.first).to_have_attribute("href", "https://curiosity.live/courses-details/good")
    expect(links.first).to_contain_text("Good <b>course</b>")


# ---- failures --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status, message",
    [(500, "The assistant had a problem"), (429, "Too many questions right now"), (422, "Try shorter wording")],
)
def test_server_errors_are_explained(page, server, status, message):
    open_demo(page, server)
    page.route("**/chat", lambda route: route.fulfill(status=status, json={"detail": "x"}))
    ask(page, "python")
    expect(page.get_by_text(message)).to_be_visible()
    expect(page.get_by_role("button", name="Try again")).to_be_visible()


def test_try_again_recovers_after_a_network_failure(page, server):
    open_demo(page, server)
    calls = []

    def handler(route):
        calls.append(1)
        route.abort() if len(calls) == 1 else route.continue_()

    page.route("**/chat", handler)
    ask(page, "python")
    expect(page.get_by_text("Could not reach the assistant")).to_be_visible()
    page.get_by_role("button", name="Try again").click()
    expect(page.get_by_text("You could start with Python for Beginners.")).to_be_visible()
    expect(page.get_by_text("Could not reach the assistant")).to_have_count(0)
    assert len(calls) == 2
    expect(page.get_by_text("python", exact=True)).to_have_count(1)  # the question is not shown twice


# ---- keeping the conversation, keyboard, small screens ----------------------------------------


def test_conversation_and_session_survive_a_page_change(page, server):
    open_demo(page, server)
    with page.expect_response("**/chat") as first:
        ask(page, "python")
    session_id = first.value.json()["session_id"]
    expect(page.get_by_text("You could start with Python for Beginners.")).to_be_visible()
    page.reload()
    expect(dialog(page)).to_be_visible()  # reopened where the user left it
    expect(page.get_by_text("You could start with Python for Beginners.")).to_be_visible()
    expect(page.get_by_role("button", name="Python courses")).to_have_count(0)
    with page.expect_request("**/chat") as second:
        ask(page, "excel")
    assert second.value.post_data_json == {"message": "excel", "session_id": session_id}


def test_escape_closes_and_returns_focus_to_the_launcher(page, server):
    open_demo(page, server)
    box(page).press("Escape")
    expect(dialog(page)).to_be_hidden()
    expect(launcher(page)).to_be_visible()
    assert launcher(page).evaluate("e => e.getRootNode().activeElement === e")
    page.evaluate("CuriosityChat.open()")  # page scripts can open it too
    expect(dialog(page)).to_be_visible()
    page.get_by_role("button", name="Close chat").click()
    expect(dialog(page)).to_be_hidden()


def test_phone_screen_uses_full_screen_with_no_sideways_scroll(browser, server):
    context = browser.new_context(viewport={"width": 375, "height": 667}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.set_default_timeout(5000)
    page.goto(server + "/demo")
    launcher(page).tap()
    size = dialog(page).bounding_box()
    assert abs(size["width"] - 375) <= 1 and abs(size["height"] - 667) <= 1
    assert box(page).evaluate("e => getComputedStyle(e).fontSize") == "16px"  # avoids iOS zoom on focus
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    for name in ["Send message", "Close chat"]:
        target = page.get_by_role("button", name=name).bounding_box()
        assert target["width"] >= 43.9 and target["height"] >= 43.9  # 44 px: comfortable for a thumb
    context.close()


# ---- settings and the real cross-origin setup ----------------------------------------------------


def test_settings_come_from_script_attributes(page, stack):
    attrs = 'data-color="#ff6600" data-title="Help" data-label="Ask us" data-position="left" data-suggestions="One|Two"'
    page.goto(with_attrs(stack.lms, attrs))
    button = page.get_by_role("button", name="Ask us")
    expect(button).to_be_visible()
    assert button.bounding_box()["x"] < 100  # left side
    colours = button.evaluate("e => { const s = getComputedStyle(e); return [s.backgroundColor, s.color]; }")
    assert colours == ["rgb(255, 102, 0)", "rgb(16, 21, 28)"]  # dark text, because it reads better on orange
    button.click()
    expect(dialog(page, "Help")).to_be_visible()
    expect(page.locator(".chip")).to_have_count(2)


def test_bad_color_value_cannot_inject_css(page, stack):
    page.goto(with_attrs(stack.lms, 'data-color="red;}body{display:none"'))
    expect(launcher(page)).to_be_visible()
    assert launcher(page).evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(13, 110, 253)"
    assert page.evaluate("getComputedStyle(document.body).display") != "none"


def test_works_from_the_allowed_lms_origin(page, stack):
    """The real setup: the page is on the LMS site and the API is on another host (CORS)."""
    page.goto(with_attrs(stack.lms))
    assert stack.lms != stack.api
    launcher(page).click()
    ask(page, "leadership skills")
    expect(page.get_by_text("You could start with Servant Leadership.")).to_be_visible()
    link = page.get_by_role("link", name=re.compile("Servant Leadership"))
    expect(link).to_have_attribute("href", stack.lms + "/courses-details/servant-leadership")
    assert page.js_errors == []


def test_other_websites_cannot_use_the_api(page, stack):
    page.goto(with_attrs(stack.other))
    launcher(page).click()
    ask(page, "python")
    expect(page.get_by_text("Could not reach the assistant")).to_be_visible()


# ---- the real site's constraints: strict CSP and a service worker -----------------------------

STRICT_CSP = "default-src 'self'; script-src 'self' {api}; connect-src 'self' {api}; style-src 'self'"


def test_works_under_a_strict_csp_without_unsafe_inline_styles(page, stack):
    page.goto(with_attrs(stack.lms, extra="&csp=" + quote(STRICT_CSP, safe="")))
    expect(launcher(page)).to_be_visible()
    # Styled for real: the launcher floats (position: fixed) instead of sitting in page flow.
    assert launcher(page).evaluate("el => getComputedStyle(el).position") == "fixed"
    launcher(page).click()
    expect(dialog(page)).to_be_visible()
    ask(page, "python")
    expect(page.get_by_text("You could start with Python for Beginners.")).to_be_visible()
    assert page.js_errors == []


def test_csp_that_omits_the_chatbot_host_blocks_the_widget(page, stack):
    """Negative control: proves the strict-CSP test above really enforces the policy."""
    page.goto(with_attrs(stack.lms, extra="&csp=" + quote("default-src 'self'", safe="")))
    page.wait_for_timeout(500)
    expect(launcher(page)).to_have_count(0)


def test_works_when_a_service_worker_controls_the_page(page, stack):
    page.goto(with_attrs(stack.lms, extra="&sw=1"))
    page.wait_for_function("navigator.serviceWorker.controller !== null || true")
    page.evaluate("navigator.serviceWorker.ready")
    page.reload()
    assert page.evaluate("!!navigator.serviceWorker.controller")
    expect(launcher(page)).to_be_visible()
    launcher(page).click()
    ask(page, "python")
    expect(page.get_by_text("You could start with Python for Beginners.")).to_be_visible()


# ---- Curi-Assist: departments and website help --------------------------------------------------


def test_listing_courses_asks_for_a_department_then_lists_its_courses(page, stack):
    page.goto(with_attrs(stack.lms))
    launcher(page).click()
    ask(page, "list me all the courses you have")
    expect(page.get_by_text("Which department are you interested in?")).to_be_visible()
    for name in ["Programming (1)", "Business (1)", "Office Productivity (1)"]:
        expect(page.get_by_role("button", name=name)).to_be_visible()
    page.get_by_role("button", name="Business (1)").click()
    expect(page.get_by_text("Business has 1 course.")).to_be_visible()
    expect(page.get_by_role("link", name=re.compile("Servant Leadership"))).to_be_visible()
    expect(page.get_by_role("button", name="Programming (1)")).to_have_count(0)  # old buttons are replaced
    page.get_by_role("button", name="Other departments").click()
    expect(page.get_by_role("button", name="Programming (1)")).to_be_visible()
    assert page.js_errors == []


def test_website_help_gives_a_direct_link(page, stack):
    page.goto(with_attrs(stack.lms))
    launcher(page).click()
    ask(page, "where can i create my account")
    link = page.get_by_role("link", name=re.compile("Create your account"))
    expect(link).to_be_visible()
    expect(link).to_have_attribute("href", stack.lms + "/register")
    assert page.js_errors == []
