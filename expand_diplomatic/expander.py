"""Core logic: expand XML via Gemini. load/save_examples live in examples_io."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from lxml import etree


class ExpandCancelled(Exception):
    """Raised when expansion is cancelled by the user."""


def _get_max_concurrent(backend: str) -> int:
    """Max parallel block expansions. Env EXPANDER_MAX_CONCURRENT overrides."""
    v = os.environ.get("EXPANDER_MAX_CONCURRENT", "").strip()
    if v:
        try:
            return max(1, min(16, int(v)))
        except ValueError:
            pass
    return 6 if backend == "local" else 2

# TEI-style block elements + PAGE Unicode (local names, any namespace)
TEXT_BLOCK_TAGS = frozenset({"p", "ab", "l", "seg", "item", "td", "th", "figDesc", "head", "Unicode"})


def _escape_xml_text(s: str) -> str:
    """Escape text for safe inclusion in XML."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def get_block_ranges(xml_source: str, block_tags: set[str] | None = None) -> list[tuple[int, int]]:
    """
    Return (start, end) character ranges for each block element in the XML string.
    Used to map click position to block index for input/output sync.
    """
    tags = block_tags or TEXT_BLOCK_TAGS
    try:
        root = etree.fromstring(xml_source.encode("utf-8"), etree.XMLParser(recover=True, remove_blank_text=False))
    except etree.XMLSyntaxError:
        return []
    ranges: list[tuple[int, int]] = []
    search_start = 0

    def local_name(el: etree._Element) -> str:
        return etree.QName(el).localname if el.tag is not None else ""

    for el in root.iter():
        if local_name(el) not in tags:
            continue
        if _has_descendant_block(el, tags):
            continue
        content = (_inner_text(el) or "").strip()
        if not content:
            continue
        # Try fragment match first (works when serialization matches)
        frag = etree.tostring(el, encoding="unicode", method="xml")
        idx = xml_source.find(frag, search_start)
        if idx < 0:
            # Fallback: search for ">content</" (handles namespaced XML)
            escaped = _escape_xml_text(content)
            needle = ">" + escaped + "</"
            pos = xml_source.find(needle, search_start)
            if pos >= 0:
                start = xml_source.rfind("<", 0, pos + 1)
                end = xml_source.find(">", pos + len(needle)) + 1
                if start >= 0 and end > start:
                    idx = start
                    frag = xml_source[start:end]
        if idx >= 0:
            ranges.append((idx, idx + len(frag)))
            search_start = idx + len(frag)
    return ranges


def extract_expansion_pairs(
    xml_input: str,
    xml_output: str,
    block_tags: set[str] | None = None,
) -> list[dict[str, str]]:
    """
    Extract (diplomatic, full) pairs from input and output XML.
    Pairs blocks by index; only includes pairs where text changed.
    Used for auto-learning from Gemini expansion results.
    """
    tags = block_tags or TEXT_BLOCK_TAGS

    parser = etree.XMLParser(recover=True, remove_blank_text=False)

    def get_blocks(xml_str: str) -> list[str]:
        try:
            root = etree.fromstring(xml_str.encode("utf-8"), parser)
        except etree.XMLSyntaxError:
            return []

        def local_name(el: etree._Element) -> str:
            return etree.QName(el).localname if el.tag is not None else ""

        blocks = []
        for el in root.iter():
            if local_name(el) not in tags:
                continue
            if _has_descendant_block(el, tags):
                continue
            raw = _inner_text(el)
            if raw.strip():
                blocks.append(raw.strip())
        return blocks

    inp_blocks = get_blocks(xml_input)
    out_blocks = get_blocks(xml_output)
    pairs = []
    for i, (dip, full) in enumerate(zip(inp_blocks, out_blocks)):
        if dip != full and dip and full:
            pairs.append({"diplomatic": dip, "full": full})
    return pairs


def extract_text_lines(xml_source: str, block_tags: set[str] | None = None) -> str:
    """
    Extract text from XML block elements (p, ab, Unicode, etc.), one line per block.
    Returns plain text suitable for saving as .txt.
    """
    tags = block_tags or TEXT_BLOCK_TAGS
    try:
        root = etree.fromstring(xml_source.encode("utf-8"), etree.XMLParser(recover=True, remove_blank_text=False))
    except etree.XMLSyntaxError:
        return ""
    lines: list[str] = []

    def local_name(el: etree._Element) -> str:
        return etree.QName(el).localname if el.tag is not None else ""

    for el in root.iter():
        if local_name(el) not in tags:
            continue
        if _has_descendant_block(el, tags):
            continue
        raw = _inner_text(el)
        if raw.strip():
            lines.append(raw.strip())
    return "\n".join(lines)

MODALITIES = ("full", "conservative", "normalize", "aggressive", "local")
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
    "local": (
        "Expand diplomatic transcriptions: resolve abbreviations and superscripts."
        + _LATIN
        + " Output only the expanded text, no XML, no commentary. Use the examples as your guide."
    ),
}


def _build_prompt_prefix(examples: list[dict[str, str]], modality: str = "full") -> str:
    """Build system + examples once; append block text per call. For local backend."""
    system = MODALITY_SYSTEM.get(modality) or MODALITY_SYSTEM["full"]
    parts = [system, ""]
    for ex in examples:
        parts.append("Diplomatic:")
        parts.append(ex["diplomatic"])
        parts.append("Full:")
        parts.append(ex["full"])
        parts.append("")
    parts.append("Diplomatic:")
    return "\n".join(parts)


def _build_prompt_prefix_examples_only(examples: list[dict[str, str]]) -> str:
    """Build examples section only (no modality). For Gemini with system_instruction."""
    parts = []
    for ex in examples:
        parts.append("Diplomatic:")
        parts.append(ex["diplomatic"])
        parts.append("Full:")
        parts.append(ex["full"])
        parts.append("")
    parts.append("Diplomatic:")
    return "\n".join(parts)


def _build_prompt(examples: list[dict[str, str]], text: str, modality: str = "full") -> str:
    return _build_prompt_prefix(examples, modality) + text + "\nFull:"


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
    prompt_prefix: str | None = None,
) -> str:
    if not text or not text.strip():
        return text
    prompt = (prompt_prefix + text + "\nFull:") if prompt_prefix else _build_prompt(examples, text, modality=modality)
    if backend == "local":
        from .local_llm import run_local

        return run_local(text, examples, prompt, model=model)
    from run_gemini import run_gemini

    system = MODALITY_SYSTEM.get(modality) or MODALITY_SYSTEM["full"]
    return run_gemini(
        prompt,
        model=model,
        api_key=api_key,
        temperature=0.2,
        system_instruction=system,
        client=client,
        uploaded_file=uploaded_file,
    )


def _serialize_root(root: etree._Element) -> str:
    """Serialize root to XML string."""
    out = etree.tostring(
        root,
        encoding="unicode",
        pretty_print=False,
        xml_declaration=False,
    )
    if out.strip().lower().startswith("<?xml"):
        return out
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + out


def expand_xml(
    xml_source: str,
    examples: list[dict[str, str]],
    model: str = "gemini-2.5-flash",
    api_key: str | None = None,
    block_tags: set[str] | None = None,
    input_file_path: Path | None = None,
    dry_run: bool = False,
    *,
    backend: str = "gemini",
    modality: str = "full",
    progress_callback: Callable[[int, int, str], None] | None = None,
    partial_result_callback: Callable[[str], None] | None = None,
    max_concurrent: int | None = None,
    passes: int = 1,
    cancel_check: Callable[[], bool] | None = None,
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
    - progress_callback: optional (current, total, message) -> None, called before each block.
    - partial_result_callback: optional (xml_string) -> None, called after each block with current XML.
    - max_concurrent: max parallel blocks (default from EXPANDER_MAX_CONCURRENT env or 2 gemini / 6 local).
    - passes: number of expansion passes (default 1). When > 1, re-expands output to refine further.
    - cancel_check: optional () -> bool; if returns True, expansion stops and raises ExpandCancelled.
    """
    passes = max(1, min(5, passes))
    current = xml_source
    for pass_num in range(passes):
        def _wrap_progress(cb, p: int, total_p: int):
            if cb is None:
                return None
            def wrapped(cur: int, tot: int, msg: str) -> None:
                cb(cur, tot, f"Pass {p + 1}/{total_p}: {msg}" if total_p > 1 else msg)
            return wrapped
        pcb = _wrap_progress(progress_callback, pass_num, passes)
        current = _expand_once(
            current,
            examples,
            model=model,
            api_key=api_key,
            block_tags=block_tags,
            input_file_path=input_file_path if pass_num == 0 else None,
            dry_run=dry_run,
            backend=backend,
            modality=modality,
            progress_callback=pcb,
            partial_result_callback=partial_result_callback,
            max_concurrent=max_concurrent,
            cancel_check=cancel_check,
        )
    return current


def _expand_once(
    xml_source: str,
    examples: list[dict[str, str]],
    model: str = "gemini-2.5-flash",
    api_key: str | None = None,
    block_tags: set[str] | None = None,
    input_file_path: Path | None = None,
    dry_run: bool = False,
    *,
    backend: str = "gemini",
    modality: str = "full",
    progress_callback: Callable[[int, int, str], None] | None = None,
    partial_result_callback: Callable[[str], None] | None = None,
    max_concurrent: int | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> str:
    """Single expansion pass. Used internally by expand_xml for recursive correction."""
    tags = block_tags or TEXT_BLOCK_TAGS
    root = etree.fromstring(xml_source.encode("utf-8"), etree.XMLParser(recover=True, remove_blank_text=False))

    def local_name(el: etree._Element) -> str:
        return etree.QName(el).localname if el.tag is not None else ""

    blocks: list[tuple[etree._Element, str]] = []
    for el in root.iter():
        if local_name(el) not in tags:
            continue
        if _has_descendant_block(el, tags):
            continue
        raw = _inner_text(el)
        if not raw.strip():
            continue
        blocks.append((el, raw))

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

    total = len(blocks)
    max_concurrent = max_concurrent if max_concurrent is not None else (_get_max_concurrent(backend) if not dry_run else 1)
    # When using Files API, use sequential to avoid shared client issues
    if client is not None and uploaded_file is not None:
        max_concurrent = 1
    # Prebuild prompt prefix: Gemini uses examples-only + system_instruction; local uses combined.
    prompt_prefix: str | None = None
    if not dry_run and total > 0:
        prompt_prefix = (
            _build_prompt_prefix_examples_only(examples)
            if backend == "gemini"
            else _build_prompt_prefix(examples, modality)
        )

    def expand_one(args: tuple[int, Any, str]) -> tuple[int, Any, str]:
        i, el, raw = args
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
                prompt_prefix=prompt_prefix,
            )
        return (i, el, expanded)

    def _check_cancel() -> None:
        if cancel_check is not None and cancel_check():
            raise ExpandCancelled("Expansion cancelled by user.")

    try:
        if max_concurrent <= 1 or total <= 1:
            # Sequential
            for i, (el, raw) in enumerate(blocks):
                _check_cancel()
                if progress_callback is not None:
                    progress_callback(i + 1, total, "Expanding…")
                _, el, expanded = expand_one((i, el, raw))
                _set_inner_text(el, expanded)
                if partial_result_callback is not None:
                    partial_result_callback(_serialize_root(root))
        else:
            # Parallel: submit all, apply results in order as they arrive
            results: list[tuple[Any, str] | None] = [None] * total
            next_to_apply = 0

            with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                futures = {
                    executor.submit(expand_one, (i, el, raw)): i
                    for i, (el, raw) in enumerate(blocks)
                }
                for future in as_completed(futures):
                    _check_cancel()
                    i, el, expanded = future.result()
                    results[i] = (el, expanded)
                    # Apply in order, calling progress and partial callback
                    while next_to_apply < total and results[next_to_apply] is not None:
                        el_a, expanded_a = results[next_to_apply]
                        _set_inner_text(el_a, expanded_a)
                        if progress_callback is not None:
                            progress_callback(next_to_apply + 1, total, "Expanding…")
                        # Stream updates; throttle when many blocks to reduce serialization cost
                        if partial_result_callback is not None and (
                            next_to_apply == total - 1 or total <= 8 or next_to_apply % 2 == 1
                        ):
                            partial_result_callback(_serialize_root(root))
                        next_to_apply += 1
    finally:
        if client is not None and uploaded_file is not None:
            from run_gemini import close_file_session

            close_file_session(client, uploaded_file, delete=True)

    return _serialize_root(root)
