"""Expand diplomatic transcriptions to full form via Gemini API."""

from ._version import __version__
from .examples_io import load_examples, save_examples
from .expander import expand_xml

__all__ = ["expand_xml", "load_examples", "save_examples"]
