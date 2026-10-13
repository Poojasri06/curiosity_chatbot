"""Settings, read from environment variables (see .env.example)."""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field

# Free-tier providers that speak the OpenAI chat format. Defaults come from each
# provider's official docs; override with LLM_BASE_URL / LLM_MODEL if they change.
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.5-flash-lite",
        "key_env": "GEMINI_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-20b",
        "key_env": "GROQ_API_KEY",
    },
    # Any other OpenAI-compatible service (OpenRouter, Mistral, a local Ollama...):
    # LLM_BASE_URL and LLM_MODEL are required.
    "openai_compatible": {"base_url": "", "model": "", "key_env": ""},
}


def load_dotenv(path: str | Path, environ=None) -> int:
    """Reads KEY=value lines from a .env file into the environment.

    Variables already set in the environment win, so hosting dashboards (Render) still override it.
    Returns how many variables were loaded. A missing file is fine.
    """
    environ = os.environ if environ is None else environ
    path = Path(path)
    if not path.is_file():
        return 0
    loaded = 0
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].strip()
        if key and key not in environ:
            environ[key] = value
            loaded += 1
    return loaded


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "Curiosity LMS Chatbot"
    # "echo" (no key, for testing), "gemini", "groq" or "openai_compatible".
    llm_provider: str = "echo"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout: float = 20.0
    # Course data exported from the LMS (see scripts/export_courses.py).
    courses_path: str = "data/courses.json"
    # Where course pages live, e.g. https://curiosity.live. Empty gives relative links
    # (/courses-details/<slug>), which work when the widget runs on the LMS site itself.
    lms_base_url: str = ""
    course_path: str = "/courses-details/{slug}"
    quiz_path: str = "/quiz-details/{slug}"
    # Websites allowed to call the API from a browser (the LMS widget).
    allowed_origins: list[str] = field(default_factory=list)
    # Serve /demo, a sample page with the widget on it. Keep off in production.
    demo_page: bool = False
    # Limits per visitor address and for the whole service. 0 turns a limit off.
    rate_per_minute: int = 10
    rate_per_day: int = 150
    rate_global_per_day: int = 2000


def load_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "echo").strip().lower()
    key_env = PROVIDER_DEFAULTS.get(provider, {}).get("key_env", "")
    api_key = os.getenv("LLM_API_KEY") or (os.getenv(key_env) if key_env else "") or ""
    return Settings(
        llm_provider=provider,
        llm_api_key=api_key.strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "20")),
        courses_path=os.getenv("COURSES_PATH", "data/courses.json").strip(),
        lms_base_url=os.getenv("LMS_BASE_URL", "").strip().rstrip("/"),
        course_path=os.getenv("COURSE_PATH", "").strip() or "/courses-details/{slug}",
        quiz_path=os.getenv("QUIZ_PATH", "").strip() or "/quiz-details/{slug}",
        rate_per_minute=int(os.getenv("RATE_PER_MINUTE", "10")),
        rate_per_day=int(os.getenv("RATE_PER_DAY", "150")),
        rate_global_per_day=int(os.getenv("RATE_GLOBAL_PER_DAY", "2000")),
        allowed_origins=_split(os.getenv("ALLOWED_ORIGINS", "")),
        demo_page=os.getenv("DEMO_PAGE", "").strip().lower() in {"1", "true", "yes", "on"},
    )
