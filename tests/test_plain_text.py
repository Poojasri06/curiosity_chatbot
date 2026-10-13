from app.answer import plain_text
from app.prompts import SYSTEM_PROMPT


def test_removes_bold_and_star_bullets():
    raw = "Here is a course:\n* **AI agency developer**: builds apps.\n* *Python* basics"
    out = plain_text(raw)
    assert "*" not in out
    assert out == "Here is a course:\n- AI agency developer: builds apps.\n- Python basics"


def test_removes_headings_backticks_and_extra_blank_lines():
    assert plain_text("## Title\n\n\n\nUse `pip`.") == "Title\n\nUse pip."


def test_plain_sentences_are_untouched():
    text = "The best place to start is Python for Beginners. It is free!"
    assert plain_text(text) == text


def test_prompt_asks_for_warmth_confidence_and_no_markdown():
    lowered = SYSTEM_PROMPT.lower()
    assert "warm" in lowered and "confiden" in lowered and "never use asterisks" in lowered
