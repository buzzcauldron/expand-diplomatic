from expand_diplomatic.groq_llm import _get_api_key
import pytest


def test_groq_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert _get_api_key(None) == "gsk_test"


def test_groq_key_missing(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("TRANSCRIBER_SHELL_GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        _get_api_key(None)
