from fastapi.testclient import TestClient

from app.catalogue import Catalogue
from app.config import Settings, load_settings
from app.main import create_app
from app.ratelimit import RateLimiter


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def test_blocks_after_limit_and_recovers_after_window():
    clock = Clock()
    limiter = RateLimiter(2, 60, clock=clock)
    assert limiter.check("a") == 0 and limiter.check("a") == 0
    assert limiter.check("a") > 0
    assert limiter.check("b") == 0  # other visitors are unaffected
    clock.now = 61
    assert limiter.check("a") == 0


def test_zero_turns_the_limit_off():
    limiter = RateLimiter(0, 60)
    assert all(limiter.check("a") == 0 for _ in range(100))


def test_idle_keys_are_dropped_to_bound_memory():
    clock = Clock()
    limiter = RateLimiter(5, 60, clock=clock, max_keys=3)
    for i in range(4):
        limiter.check(str(i))
    clock.now = 100
    limiter.check("new")
    assert len(limiter._hits) == 1


def make(**kw):
    return TestClient(create_app(Settings(**kw), catalogue=Catalogue([])))


def test_chat_returns_429_with_retry_after():
    client = make(rate_per_minute=2)
    for _ in range(2):
        assert client.post("/chat", json={"message": "hi"}).status_code == 200
    blocked = client.post("/chat", json={"message": "hi"})
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1


def test_global_daily_cap_applies_to_everyone():
    client = make(rate_per_minute=0, rate_per_day=0, rate_global_per_day=1)
    assert client.post("/chat", json={"message": "hi"}).status_code == 200
    assert client.post("/chat", json={"message": "hi"}).status_code == 429


def test_health_and_widget_are_not_limited():
    client = make(rate_per_minute=1)
    for _ in range(5):
        assert client.get("/health").status_code == 200
        assert client.get("/widget.js").status_code == 200


def test_limits_read_environment(monkeypatch):
    monkeypatch.setenv("RATE_PER_MINUTE", "3")
    monkeypatch.setenv("RATE_GLOBAL_PER_DAY", "0")
    s = load_settings()
    assert s.rate_per_minute == 3 and s.rate_global_per_day == 0
