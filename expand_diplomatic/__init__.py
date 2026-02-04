"""Expand Latin manuscript abbreviations into full Latin words for highly accurate transcripts (Gemini API or local Ollama)."""

from ._version import __version__
from .examples_io import add_learned_pairs, clear_examples_cache, get_learned_path, load_examples, load_learned, save_examples
from .expander import expand_xml, extract_expansion_pairs, extract_text_lines, get_block_ranges, is_page_xml, pairs_to_word_level

__all__ = [
    "add_learned_pairs",
    "clear_examples_cache",
    "expand_xml",
    "extract_expansion_pairs",
    "extract_text_lines",
    "pairs_to_word_level",
    "get_block_ranges",
    "get_learned_path",
    "is_page_xml",
    "load_examples",
    "load_learned",
    "save_examples",
]
