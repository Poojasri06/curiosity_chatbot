"""Curiosity LMS chatbot API: a health check and one chat endpoint."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .answer import Answerer
from .catalogue import Catalogue
from .config import Settings, load_dotenv, load_settings
from .llm import LLMProvider, get_provider
from .ratelimit import RateLimiter
from .schemas import ChatRequest, ChatResponse

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # do not log every AI request URL

WIDGET_DIR = Path(__file__).resolve().parent.parent / "widget"


def create_app(
    settings: Settings | None = None,
    catalogue: Catalogue | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    catalogue = catalogue if catalogue is not None else Catalogue.from_file(settings.courses_path)
    provider = provider or get_provider(settings)
    answerer = Answerer(catalogue, provider, settings)

    per_minute = RateLimiter(settings.rate_per_minute, 60)
    per_day = RateLimiter(settings.rate_per_day, 86400)
    global_day = RateLimiter(settings.rate_global_per_day, 86400)

    app = FastAPI(title=settings.app_name, version="0.3.0")

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.get("/health")
    def health() -> dict[str, str | int]:
        return {"status": "ok", "provider": provider.name, "courses": len(catalogue)}

    @app.get("/widget.js", include_in_schema=False)
    def widget_js() -> FileResponse:
        path = WIDGET_DIR / "widget.js"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="widget.js not found")
        # Short cache so fixes reach the LMS quickly.
        return FileResponse(path, media_type="application/javascript", headers={"Cache-Control": "public, max-age=300"})

    if settings.demo_page:

        @app.get("/demo", include_in_schema=False)
        def demo() -> FileResponse:
            return FileResponse(WIDGET_DIR / "demo.html", media_type="text/html")

    @app.post("/chat", response_model=ChatResponse)
    def chat(request: ChatRequest, http: Request) -> ChatResponse:
        visitor = http.client.host if http.client else "unknown"
        wait = max(per_minute.check(visitor), per_day.check(visitor), global_day.check("all"))
        if wait:
            raise HTTPException(status_code=429, detail="Too many requests", headers={"Retry-After": str(int(wait))})
        session_id = request.session_id or uuid4().hex
        result = answerer.answer(request.message, request.category, request.offset)
        return ChatResponse(answer=result.text, session_id=session_id, sources=result.sources, mode=result.mode, choices=result.choices)

    return app


if "pytest" not in sys.modules:  # tests set their own settings
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
app = create_app()
