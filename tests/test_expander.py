"""Basic tests for expand_diplomatic."""

from expand_diplomatic.examples_io import load_examples
from expand_diplomatic.expander import (
    _build_prompt,
    _build_prompt_prefix,
    expand_xml,
    get_block_ranges,
    extract_expansion_pairs,
    extract_text_lines,
)
from expand_diplomatic.local_llm import run_local_rules


def test_load_examples() -> None:
    ex = load_examples("examples.json")
    assert len(ex) >= 1
    assert "diplomatic" in ex[0] and "full" in ex[0]


def test_build_prompt_prefix() -> None:
    ex = [{"diplomatic": "a", "full": "b"}]
    p = _build_prompt_prefix(ex, "full")
    assert "Diplomatic:" in p
    assert "a" in p
    assert "Full:" in p
    assert "b" in p


def test_build_prompt() -> None:
    ex = [{"diplomatic": "a", "full": "b"}]
    p = _build_prompt(ex, "hello", "full")
    assert p.endswith("hello\nFull:")
    assert "a" in p and "b" in p


def test_run_local_rules() -> None:
    assert run_local_rules("", []) == ""
    assert run_local_rules("x", []) == "x"
    assert run_local_rules("y^e", [{"diplomatic": "y^e", "full": "the"}]) == "the"
    # NFC/NFD: gratia (precomposed ã vs a+combining tilde) both match
    assert run_local_rules("grã", [{"diplomatic": "grã", "full": "gratia"}]) == "gratia"
    assert run_local_rules("gra\u0303", [{"diplomatic": "grã", "full": "gratia"}]) == "gratia"
    # et cetera (⁊c̃)
    assert run_local_rules("⁊c̃", [{"diplomatic": "⁊c̃", "full": "et cetera"}]) == "et cetera"


def test_expand_xml_dry_run() -> None:
    xml = '<?xml version="1.0"?><root><p>test</p></root>'
    ex = load_examples("examples.json")
    out = expand_xml(xml, ex, dry_run=True)
    assert "test" in out
    assert "<p>" in out


def test_expand_xml_local() -> None:
    xml = '<?xml version="1.0"?><root><p>y^e same</p></root>'
    ex = [{"diplomatic": "y^e", "full": "the"}]
    out = expand_xml(xml, ex, backend="local")
    assert "the" in out or "same" in out


def test_expand_xml_rules() -> None:
    """Rules-only backend expands via examples only (no Ollama)."""
    xml = '<?xml version="1.0"?><root><p>y^e same</p></root>'
    ex = [{"diplomatic": "y^e", "full": "the"}]
    out = expand_xml(xml, ex, backend="rules")
    assert "the" in out
    assert "y^e" not in out


def test_expand_xml_invalid_raises() -> None:
    """Invalid/non-XML input raises clear error (lxml recover=True can return None)."""
    import pytest
    ex = [{"diplomatic": "a", "full": "b"}]
    with pytest.raises(ValueError, match="Invalid or empty XML"):
        expand_xml("-", ex, backend="local")
    with pytest.raises(ValueError, match="Invalid or empty XML"):
        expand_xml("{}", ex, backend="local")


def test_get_block_ranges_invalid_returns_empty() -> None:
    assert get_block_ranges("-") == []
    assert get_block_ranges("{}") == []


def test_extract_expansion_pairs_invalid_returns_empty() -> None:
    assert extract_expansion_pairs("-", "<x>y</x>") == []
    assert extract_expansion_pairs("<x>a</x>", "{}") == []


def test_extract_text_lines_invalid_returns_empty() -> None:
    assert extract_text_lines("-") == ""
    assert extract_text_lines("{}") == ""
