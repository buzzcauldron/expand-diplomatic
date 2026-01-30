"""Core logic: expand XML via Gemini. load/save_examples live in examples_io."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lxml import etree

# TEI-style block elements + PAGE Unicode (local names, any namespace)
TEXT_BLOCK_TAGS = frozenset({"p", "ab", "l", "seg", "item", "td", "th", "figDesc", "head", "Unicode"})

MODALITIES = ("full", "conservative", "normalize", "aggressive")
_LATIN = " Keep the full (expanded) form in Latin. Do not translate to English or any other language."
MODALITY_SYSTEM: dict[str, str] = {
    "full": (
        "You expand diplomatic transcriptions into full, readable form. "
        "Resolve abbreviations, expand superscripts, normalize punctuation and spacing."
        + _LATIN + " Output only the expanded text, no XML, no commentary."
    ),
    "conservative": (
        "Expand abbreviations and superscripts only. Keep original wording, punctuation, and spelling where possible. "
        "Do not modernize or paraphrase."
        + _LATIN + " Output only the expanded text, no XML, no commentary."
    ),
    "normalize": (
        "Normalize spacing and punctuation; expand common abbreviations and superscripts. "
        "Keep the text close to the diplomatic form."
        + _LATIN + " Output only the expanded text, no XML, no commentary."
    ),
    "aggressive": (
        "Fully expand to modern, readable Latin prose. Resolve all abbreviations, expand superscripts, "
        "normalize punctuation and spacing, and lightly modernize wording where it aids clarity."
        + _LATIN + " Output only the expanded text, no XML, no commentary."
    ),
}


def _build_prompt(examples: list[dict[str, str]], text: str, modality: str = "full") -> str:
    system = MODALITY_SYSTEM.get(modality) or MODALITY_SYSTEM["full"]
    parts = [system, ""]
    for ex in examples:
        parts.append("Diplomatic:")
        parts.append(ex["diplomatic"])
        parts.append("Full:")
        parts.append(ex["full"])
        parts.append("")
    parts.append("Diplomatic:")
    parts.append(text)
    parts.append("Full:")
    return "\n".join(parts)


def _inner_text(el: etree._Element) -> str:
    return "".join(el.itertext())


def _set_inner_text(el: etree._Element, text: str) -> None:
    """Replace element content with a single text node. Preserves tag and attributes."""
    for c in list(el):
        el.remove(c)
    el.text = text


def _has_descendant_block(el: etree._Element, tags: set[str]) -> bool:
    def local(e: etree._Element) -> str:
        return etree.QName(e).localname if e.tag is not None else ""

    for child in el.iter():
        if child is el:
            continue
        if local(child) in tags:
            return True
    return False


def _expand_text_block(
    text: str,
    examples: list[dict[str, str]],
    model: str,
    api_key: str | None,
    *,
    backend: str = "gemini",
    modality: str = "full",
    client: Any = None,
    uploaded_file: Any = None,
) -> str:
    if not text or not text.strip():
        return text
    prompt = _build_prompt(examples, text, modality=modality)
    if backend == "local":
        from .local_llm import run_local

        return run_local(text, examples, prompt, model=model)
    from run_gemini import run_gemini

    return run_gemini(
        prompt,
        model=model,
        api_key=api_key,
        temperature=0.2,
        client=client,
        uploaded_file=uploaded_file,
    )


def expand_xml(
    xml_source: str,
    examples: list[dict[str, str]],
    model: str = "gemini-2.5-pro",
    api_key: str | None = None,
    block_tags: set[str] | None = None,
    input_file_path: Path | None = None,
    dry_run: bool = False,
    *,
    backend: str = "gemini",
    modality: str = "full",
) -> str:
    """
    Parse XML, expand text inside block elements via LLM, return modified XML string.

    - xml_source: full XML document as string.
    - examples: list of {"diplomatic": "...", "full": "..."}.
    - model: model id (Gemini or Ollama, depending on backend).
    - api_key: override for Gemini (else uses GEMINI_API_KEY / GOOGLE_API_KEY).
    - block_tags: set of local tag names to process (default: TEI-style blocks).
    - input_file_path: when set and backend=gemini, upload via Files API and pass as context.
    - dry_run: if True, skip LLM and leave block text unchanged (for pipeline testing).
    - backend: "gemini" (default) or "local" (Ollama).
    - modality: "full" | "conservative" | "normalize" | "aggressive" — expansion style (prompt variant).
    """
    tags = block_tags or TEXT_BLOCK_TAGS
    parser = etree.XMLParser(recover=True, remove_blank_text=False)
    root = etree.fromstring(xml_source.encode("utf-8"), parser=parser)

    def local_name(el: etree._Element) -> str:
        return etree.QName(el).localname if el.tag is not None else ""

    client: Any = None
    uploaded_file: Any = None
    if (
        not dry_run
        and backend == "gemini"
        and input_file_path is not None
        and input_file_path.exists()
    ):
        from run_gemini import prepare_file_session

        client, uploaded_file = prepare_file_session(input_file_path, api_key)

    try:
        for el in root.iter():
            if local_name(el) not in tags:
                continue
            if _has_descendant_block(el, tags):
                continue
            raw = _inner_text(el)
            if not raw.strip():
                continue
            if dry_run:
                expanded = raw
            else:
                expanded = _expand_text_block(
                    raw,
                    examples,
                    model,
                    api_key,
                    backend=backend,
                    modality=modality,
                    client=client,
                    uploaded_file=uploaded_file,
                )
            _set_inner_text(el, expanded)
    finally:
        if client is not None and uploaded_file is not None:
            from run_gemini import close_file_session

            close_file_session(client, uploaded_file, delete=True)

    out = etree.tostring(
        root,
        encoding="unicode",
        pretty_print=False,
        xml_declaration=False,
    )
    if out.strip().lower().startswith("<?xml"):
        return out
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + out
