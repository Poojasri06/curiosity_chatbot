"""Request and response shapes for the chat API."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ChatRequest(BaseModel):
    message: Message
    session_id: str | None = None
    # Set when the visitor taps a department button: list that department's courses from `offset`.
    category: Annotated[str, StringConstraints(max_length=80)] | None = None
    offset: Annotated[int, Field(ge=0, le=10_000)] = 0


class Source(BaseModel):
    title: str
    url: str


class Choice(BaseModel):
    """A button shown under an answer. Tapping it sends `label` with `category` and `offset`."""

    label: str
    category: str = ""
    offset: int = 0


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    # Courses named in the answer, each with a link to its page.
    sources: list[Source] = []
    # "ai": written by the AI model. "search": the AI provider was unavailable, so the
    # answer is a plain list of matching courses.
    # "browse": a department list or the courses in one. "help": a website help answer.
    mode: Literal["ai", "search", "browse", "help"] = "ai"
    choices: list[Choice] = []
