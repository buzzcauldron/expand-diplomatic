"""Core logic: expand XML via Gemini. load/save_examples live in examples_io."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from lxml import etree

from .gemini_models import DEFAULT_MODEL as _DEFAULT_GEMINI


class ExpandCancelled(Exception):
    """Raised when expansion is cancelled by the user."""


def _get_max_concurrent(backend: str) -> int:
    """Max parallel block expansions. Env EXPANDER_MAX_CONCURRENT overrides.
    When backend=local and high-end GPU detected, default is 12."""
    v = os.environ.get("EXPANDER_MAX_CONCURRENT", "").strip()
    if v:
        try:
            return max(1, min(16, int(v)))
        except ValueError:
            pass
    if backend == "local":
        try:
            from .gpu_detect import detect_high_end_gpu
            if detect_high_end_gpu():
                return 12
        except Exception:
            pass
        return 6
    return 2

# TEI-style block elements + PAGE XML Unicode (local names, any namespace)
# PAGE XML: elements like <Unicode> inside <TextEquiv> are expanded in place
# TEI: elements like <p>, <ab>, <l>, <seg> are expanded
TEXT_BLOCK_TAGS = frozenset({"p", "ab", "l", "seg", "item", "td", "th", "figDesc", "head", "Unicode"})

# PAGE XML namespace prefix for detection
PAGE_XML_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent"


def is_page_xml(xml_source: str) -> bool:
    """Check if the XML source is PAGE XML format (has PAGE namespace)."""
    return PAGE_XML_NS in xml_source


def _escape_xml_text(s: str) -> str:
    """Escape text for safe inclusion in XML."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _local_name(el: etree._Element) -> str:
    """Local tag name for element (handles namespaces)."""
    return etree.QName(el).localname if el.tag is not None else ""


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

    for el in root.iter():
        if _local_name(el) not in tags:
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

        blocks = []
        for el in root.iter():
            if _local_name(el) not in tags:
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

    for el in root.iter():
        if _local_name(el) not in tags:
            continue
        if _has_descendant_block(el, tags):
            continue
        raw = _inner_text(el)
        if raw.strip():
            lines.append(raw.strip())
    return "\n".join(lines)

MODALITIES = ("full", "conservative", "normalize", "aggressive", "local")
_LATIN = " Keep the expanded form in Latin. Do not translate to English or any other language."
_WHOLE_DOC_OUTPUT = (
    " Return the complete XML document with diplomatic transcriptions expanded. "
    "Preserve all tags, attributes, namespaces, and structure exactly. "
    "Only change the text content inside elements. Output only the XML, no commentary or markdown."
)
MODALITY_SYSTEM: dict[str, str] = {
    "conservative": (
        "Expand manuscript diplomatic transcriptions accurately. "
        "Resolve abbreviations and superscripts only. Preserve original wording, spelling, and punctuation. "
        "Do not paraphrase or change the text beyond expansion."
        + _LATIN + " Output only the expanded text, no XML, no commentary."
    ),
    "normalize": (
        "Expand manuscript diplomatic transcriptions accurately. "
        "Resolve abbreviations and superscripts; normalize spacing and punctuation where needed. "
        "Keep the text close to the diplomatic form; do not paraphrase."
        + _LATIN + " Output only the expanded text, no XML, no commentary."
    ),
    "full": (
        "Expand manuscript diplomatic transcriptions accurately into full, readable form. "
        "Resolve abbreviations, expand superscripts, normalize punctuation and spacing. "
        "Remain faithful to the source."
        + _LATIN + " Output only the expanded text, no XML, no commentary."
    ),
    "aggressive": (
        "Expand manuscript diplomatic transcriptions accurately and fully. "
        "Resolve all abbreviations and superscripts; normalize punctuation and spacing. "
        "Produce clear, readable Latin while staying faithful to the manuscript. Do not paraphrase."
        + _LATIN + " Output only the expanded text, no XML, no commentary."
    ),
    "local": (
        "Expand manuscript diplomatic transcriptions accurately: resolve abbreviations and superscripts."
        + _LATIN
        + " Output only the expanded text, no XML, no commentary. Use the examples as your guide."
    ),
}


def _format_examples_for_prompt(examples: list[dict[str, str]]) -> str:
    """Format examples as 'Diplomatic: ... Full: ...' lines, ending with 'Diplomatic:'."""
    parts = []
    for ex in examples:
        parts.append("Diplomatic:")
        parts.append(ex["diplomatic"])
        parts.append("Full:")
        parts.append(ex["full"])
        parts.append("")
    parts.append("Diplomatic:")
    return "\n".join(parts)


def _build_prompt_prefix(examples: list[dict[str, str]], modality: str = "full") -> str:
    """Build system + examples once; append block text per call. For local backend."""
    system = MODALITY_SYSTEM.get(modality) or MODALITY_SYSTEM["full"]
    return system + "\n\n" + _format_examples_for_prompt(examples)


def _build_prompt_prefix_examples_only(examples: list[dict[str, str]]) -> str:
    """Build examples section only (no modality). For Gemini with system_instruction."""
    return _format_examples_for_prompt(examples)


def _build_prompt(examples: list[dict[str, str]], text: str, modality: str = "full") -> str:
    return _build_prompt_prefix(examples, modality) + text + "\nFull:"


def _whole_doc_system(modality: str) -> str:
    """System instruction for whole-document expansion: modality + XML output instructions."""
    base = MODALITY_SYSTEM.get(modality) or MODALITY_SYSTEM["full"]
    # Replace "Output only the expanded text" with whole-doc instruction
    base = base.replace(" Output only the expanded text, no XML, no commentary.", "")
    return base + _WHOLE_DOC_OUTPUT


_WHOLE_DOC_FILE_UPLOAD_INSTRUCTION = (
    "Here is an XML file containing diplomatic medieval Latin transcriptions "
    "(i.e. with special characters to indicate abbreviations). "
    "Please expand all abbreviations and output a valid XML file containing the full transcription. "
    "To help you, I attached a JSON file of example expansions. "
    "Do not output anything other than the contents of the XML file with the expanded abbreviations. "
    "Do not modify any part of the input XML file other than the transcriptions. "
    "Keep the expanded form in Latin. Do not translate to English."
)


def _expand_whole_document(
    xml_source: str,
    examples: list[dict[str, str]],
    model: str,
    api_key: str | None,
    modality: str = "full",
    *,
    examples_path: Path | str | None = None,
    client: Any = None,
    uploaded_file: Any = None,
) -> str:
    """Expand entire XML document in one Gemini call.
    When examples_path is provided, upload it via Files API and pass [ex_file, xml]; else embed examples in prompt.
    """
    from run_gemini import run_gemini

    examples_path = Path(examples_path) if examples_path else None
    use_file_upload = examples_path is not None and examples_path.exists()

    if use_file_upload:
        # User's pattern: upload examples file, pass [ex_file, "\n\n", input_xml]
        system = _WHOLE_DOC_FILE_UPLOAD_INSTRUCTION
        contents = xml_source
        file_path = examples_path
        temperature = 1.0
    else:
        # Fallback: embed examples in prompt
        examples_part = _format_examples_for_prompt(examples)
        contents = (
            f"{examples_part}\n"
            "Expand all diplomatic transcriptions in the following XML document.\n"
            "Return the complete XML with only the text content inside elements changed.\n\n"
            f"{xml_source}"
        )
        system = _whole_doc_system(modality)
        file_path = None
        temperature = 0.2

    result = run_gemini(
        contents,
        model=model,
        api_key=api_key,
        system_instruction=system,
        temperature=temperature,
        client=client,
        uploaded_file=uploaded_file,
        file_path=file_path,
    )
    # Strip markdown code blocks if present
    s = result.strip()
    if s.startswith("```xml"):
        s = s[6:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()

    # Validate XML; on parse failure raise helpful error
    try:
        etree.fromstring(s.encode("utf-8"), etree.XMLParser(recover=True))
    except etree.XMLSyntaxError as e:
        raise ValueError(
            f"Model returned invalid XML: {e}. Try block-by-block mode (uncheck Whole doc) or retry."
        ) from e
    return s


def _inner_text(el: etree._Element) -> str:
    return "".join(el.itertext())


def _set_inner_text(el: etree._Element, text: str) -> None:
    """Replace element content with a single text node. Preserves tag and attributes."""
    for c in list(el):
        el.remove(c)
    el.text = text


def _has_descendant_block(el: etree._Element, tags: set[str]) -> bool:
    for child in el.iter():
        if child is el:
            continue
        if _local_name(child) in tags:
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
    sorted_pairs: list[tuple[str, str]] | None = None,
    high_end_gpu: bool = False,
) -> str:
    if not text or not text.strip():
        return text
    prompt = (prompt_prefix + text + "\nFull:") if prompt_prefix else _build_prompt(examples, text, modality=modality)
    if backend == "local":
        from .local_llm import run_local

        return run_local(
            text, examples, prompt, model=model,
            sorted_pairs=sorted_pairs, high_end_gpu=high_end_gpu,
        )
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
    model: str | None = None,
    api_key: str | None = None,
    block_tags: set[str] | None = None,
    input_file_path: Path | None = None,
    examples_path: Path | str | None = None,
    dry_run: bool = False,
    *,
    backend: str = "gemini",
    modality: str = "full",
    progress_callback: Callable[[int, int, str], None] | None = None,
    partial_result_callback: Callable[[str], None] | None = None,
    max_concurrent: int | None = None,
    passes: int = 1,
    cancel_check: Callable[[], bool] | None = None,
    whole_document: bool = True,
) -> str:
    """
    Parse XML, expand text inside block elements via LLM, return modified XML string.

    - xml_source: full XML document as string.
    - examples: list of {"diplomatic": "...", "full": "..."}.
    - model: model id (Gemini or Ollama, depending on backend).
    - api_key: override for Gemini (else uses GEMINI_API_KEY / GOOGLE_API_KEY).
    - block_tags: set of local tag names to process (default: TEI-style blocks).
    - input_file_path: when set and backend=gemini (whole-doc), upload via Files API and pass as context.
    - examples_path: when set and whole-doc, upload examples JSON via Files API (user pattern: [ex_file, xml]).
    - dry_run: if True, skip LLM and leave block text unchanged (for pipeline testing).
    - backend: "gemini" (default) or "local" (Ollama).
    - modality: "full" | "conservative" | "normalize" | "aggressive" — expansion style (prompt variant).
    - progress_callback: optional (current, total, message) -> None, called before each block.
    - partial_result_callback: optional (xml_string) -> None, called after each block with current XML.
    - max_concurrent: max parallel blocks (default from EXPANDER_MAX_CONCURRENT env or 2 gemini / 6 local).
    - passes: number of expansion passes (default 1). When > 1, re-expands output to refine further.
    - cancel_check: optional () -> bool; if returns True, expansion stops and raises ExpandCancelled.
    - whole_document: when True and backend=gemini, expand entire document in one API call (default True).
    """
    if model is None:
        model = _DEFAULT_GEMINI
    passes = max(1, min(5, passes))
    current = xml_source
    for pass_num in range(passes):
        if cancel_check is not None and cancel_check():
            raise ExpandCancelled("Expansion cancelled by user.")
        if progress_callback is not None:
            msg = "Expanding whole document…" if whole_document else "Expanding…"
            if passes > 1:
                msg = f"Pass {pass_num + 1}/{passes}: {msg}"
            progress_callback(1, 1, msg)
        current = _expand_once(
            current,
            examples,
            model=model,
            api_key=api_key,
            block_tags=block_tags,
            input_file_path=input_file_path if pass_num == 0 else None,
            examples_path=examples_path,
            dry_run=dry_run,
            backend=backend,
            modality=modality,
            progress_callback=progress_callback,
            partial_result_callback=partial_result_callback,
            max_concurrent=max_concurrent,
            cancel_check=cancel_check,
            whole_document=whole_document,
        )
        if whole_document and partial_result_callback is not None:
            partial_result_callback(current)
    return current


def _expand_once(
    xml_source: str,
    examples: list[dict[str, str]],
    model: str | None = None,
    api_key: str | None = None,
    block_tags: set[str] | None = None,
    input_file_path: Path | None = None,
    examples_path: Path | str | None = None,
    dry_run: bool = False,
    *,
    backend: str = "gemini",
    modality: str = "full",
    progress_callback: Callable[[int, int, str], None] | None = None,
    partial_result_callback: Callable[[str], None] | None = None,
    max_concurrent: int | None = None,
    cancel_check: Callable[[], bool] | None = None,
    whole_document: bool = True,
) -> str:
    """Single expansion pass. Used internally by expand_xml for recursive correction."""
    if model is None:
        model = _DEFAULT_GEMINI

    if whole_document and backend == "gemini" and not dry_run:
        # When examples_path provided, upload examples file and pass [ex_file, xml]; else use input_file_path for XML if set
        client: Any = None
        uploaded_file: Any = None
        if input_file_path is not None and input_file_path.exists() and not examples_path:
            from run_gemini import prepare_file_session
            client, uploaded_file = prepare_file_session(input_file_path, api_key)
        try:
            return _expand_whole_document(
                xml_source,
                examples,
                model=model,
                api_key=api_key,
                modality=modality,
                examples_path=examples_path,
                client=client,
                uploaded_file=uploaded_file,
            )
        finally:
            if client is not None and uploaded_file is not None:
                from run_gemini import close_file_session
                close_file_session(client, uploaded_file, delete=True)

    tags = block_tags or TEXT_BLOCK_TAGS
    root = etree.fromstring(xml_source.encode("utf-8"), etree.XMLParser(recover=True, remove_blank_text=False))

    blocks: list[tuple[etree._Element, str]] = []
    for el in root.iter():
        if _local_name(el) not in tags:
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
    high_end_gpu = False
    if not dry_run and backend == "local":
        try:
            from .gpu_detect import detect_high_end_gpu
            high_end_gpu = detect_high_end_gpu()
        except Exception:
            pass
    # Prebuild prompt prefix: Gemini uses examples-only + system_instruction; local uses combined.
    prompt_prefix: str | None = None
    sorted_pairs: list[tuple[str, str]] | None = None
    if not dry_run and total > 0:
        prompt_prefix = (
            _build_prompt_prefix_examples_only(examples)
            if backend == "gemini"
            else _build_prompt_prefix(examples, modality)
        )
        if backend == "local" and examples:
            sorted_pairs = sorted(
                [(ex["diplomatic"], ex["full"]) for ex in examples],
                key=lambda p: len(p[0]),
                reverse=True,
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
                sorted_pairs=sorted_pairs,
                high_end_gpu=high_end_gpu,
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
