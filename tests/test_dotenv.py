from app.config import load_dotenv


def test_reads_values_quotes_and_comments(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\nLLM_PROVIDER=gemini\nLLM_API_KEY=\"abc 123\"\nexport DEMO_PAGE=true  \nORIGINS=a,b # note\nBROKEN\n",
        encoding="utf-8",
    )
    environ = {}
    assert load_dotenv(env_file, environ) == 4
    assert environ == {"LLM_PROVIDER": "gemini", "LLM_API_KEY": "abc 123", "DEMO_PAGE": "true", "ORIGINS": "a,b"}


def test_real_environment_wins_over_the_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=gemini\n")
    environ = {"LLM_PROVIDER": "groq"}
    assert load_dotenv(env_file, environ) == 0
    assert environ["LLM_PROVIDER"] == "groq"


def test_missing_file_is_fine(tmp_path):
    assert load_dotenv(tmp_path / "nope.env", {}) == 0
