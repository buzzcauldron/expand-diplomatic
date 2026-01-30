"""Expand diplomatic transcriptions to full form via Gemini API."""

from ._version import __version__
from .examples_io import add_learned_pairs, get_learned_path, load_examples, load_learned, save_examples
from .expander import expand_xml, extract_expansion_pairs, extract_text_lines, get_block_ranges

__all__ = [
    "add_learned_pairs",
    "expand_xml",
    "extract_expansion_pairs",
    "extract_text_lines",
    "get_block_ranges",
    "get_learned_path",
    "load_examples",
    "load_learned",
    "save_examples",
]
