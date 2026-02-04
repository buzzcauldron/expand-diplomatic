"""CLI for expand_diplomatic: expand, train (add examples locally)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from expand_diplomatic.gemini_models import DEFAULT_MODEL as _DEFAULT_GEMINI

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
_ENV_EXAMPLE = _PROJECT_ROOT / ".env.example"


def _ensure_env() -> None:
    """Create .env from .env.example if missing; then load .env."""
    if not _ENV_PATH.exists() and _ENV_EXAMPLE.exists():
        import shutil

        shutil.copy(_ENV_EXAMPLE, _ENV_PATH)
    load_dotenv(_ENV_PATH)


_ensure_env()


def _api_key_error_message() -> str:
    return (
        "GEMINI_API_KEY or GOOGLE_API_KEY is not set.\n"
        f"Edit .env at {_ENV_PATH}\n"
        "Set GEMINI_API_KEY=your-key (https://aistudio.google.com/apikey), then retry."
    )


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _run_one(
    xml_content: str,
    examples: list[dict],
    model: str,
    api_key: str | None,
    out_path: Path | None,
    *,
    backend: str = "gemini",
    modality: str = "full",
    input_file_path: Path | None = None,
    examples_path: Path | None = None,
    use_files_api: bool = False,
    dry_run: bool = False,
    max_concurrent: int | None = None,
    passes: int = 1,
    whole_document: bool = False,
    max_examples: int | None = None,
    example_strategy: str = "longest-first",
) -> None:
    from .expander import expand_xml

    input_path = input_file_path if use_files_api and backend == "gemini" else None
    result = expand_xml(
        xml_content,
        examples,
        model=model,
        api_key=api_key,
        input_file_path=input_path,
        examples_path=examples_path,
        dry_run=dry_run,
        backend=backend,
        modality=modality,
        max_concurrent=max_concurrent,
        passes=passes,
        whole_document=whole_document,
        max_examples=max_examples,
        example_strategy=example_strategy,
    )
    if out_path is not None:
        out_path.write_text(result, encoding="utf-8")
        print(f"Wrote {out_path}", file=sys.stderr)
    else:
        print(result)


def _run_train(args: argparse.Namespace) -> None:
    from .examples_io import load_examples, save_examples

    examples_path = args.examples
    try:
        existing = load_examples(examples_path)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print(f"Examples in {examples_path} ({len(existing)} pairs):", file=sys.stderr)
        for i, e in enumerate(existing, 1):
            print(f"  {i}. {e['diplomatic']!r} → {e['full']!r}", file=sys.stderr)
        return

    if args.add:
        d = (args.diplomatic or "").strip()
        f = (args.full or "").strip()
        if not d or not f:
            print("Error: --add requires both --diplomatic and --full", file=sys.stderr)
            sys.exit(1)
        existing.append({"diplomatic": d, "full": f})
        save_examples(examples_path, existing)
        print(f"Added 1 pair → {examples_path} ({len(existing)} total)", file=sys.stderr)
        return

    # Interactive loop
    print(
        "Add diplomatic → full pairs (stored locally). Empty diplomatic to quit.",
        file=sys.stderr,
    )
    print("Examples file:", examples_path, file=sys.stderr)
    while True:
        try:
            diplomatic = input("Diplomatic (empty to quit): ").strip()
        except EOFError:
            break
        if not diplomatic:
            break
        try:
            full = input("Full: ").strip()
        except EOFError:
            break
        if not full:
            print("Skipped (empty full).", file=sys.stderr)
            continue
        existing.append({"diplomatic": diplomatic, "full": full})
        save_examples(examples_path, existing)
        print(f"  → saved ({len(existing)} pairs)", file=sys.stderr)


def _prompt_api_key() -> str | None:
    """If stdin is a TTY, prompt for API key; else return None."""
    if not sys.stdin.isatty():
        return None
    try:
        print("API key not set. Paste key (or Enter to exit): ", end="", file=sys.stderr)
        line = sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        return None
    key = (line or "").strip()
    return key or None


def _run_expand(args: argparse.Namespace) -> None:
    from .examples_io import load_examples

    dry_run = getattr(args, "dry_run", False)
    backend = getattr(args, "backend", "gemini")
    api_key: str | None = getattr(args, "api_key", None) or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not dry_run and backend == "gemini" and not api_key:
        if getattr(args, "prompt_key", False) and sys.stdin.isatty():
            api_key = _prompt_api_key()
        if not api_key:
            print("Error:", _api_key_error_message(), file=sys.stderr)
            print("Use --backend local for Ollama, or --api-key KEY, or --prompt-key to ask interactively.", file=sys.stderr)
            sys.exit(1)

    model = args.model if backend == "gemini" else getattr(args, "local_model", "llama3.2")
    modality = getattr(args, "modality", "full") or "full"

    try:
        examples = load_examples(args.examples)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not examples and not dry_run:
        print(
            "Warning: no examples loaded. Add pairs via `train` or edit "
            f"{args.examples}",
            file=sys.stderr,
        )

    mc = getattr(args, "max_concurrent", None)
    if mc is not None and (mc < 1 or mc > 16):
        mc = None
    passes = getattr(args, "passes", 1) or 1
    passes = max(1, min(5, passes))
    whole_document = getattr(args, "whole_doc", False)  # Default: block-by-block

    ex_path = Path(args.examples) if whole_document and backend == "gemini" else None

    max_examples = getattr(args, "max_examples", None)
    example_strategy = getattr(args, "example_strategy", "longest-first") or "longest-first"

    def run(text: str, out: Path | None, *, fpath: Path | None = None, files_api: bool = False) -> None:
        _run_one(
            text,
            examples,
            model,
            api_key,
            out,
            backend=backend,
            modality=modality,
            input_file_path=fpath,
            examples_path=ex_path,
            use_files_api=files_api,
            dry_run=dry_run,
            max_concurrent=mc,
            passes=passes,
            whole_document=whole_document,
            max_examples=max_examples,
            example_strategy=example_strategy,
        )

    if args.text is not None:
        try:
            run(args.text, args.out)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.file is not None:
        if not args.file.exists():
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        xml = args.file.read_text(encoding="utf-8")
        out_path = args.out or (args.file.parent / f"{args.file.stem}_expanded.xml")
        try:
            run(xml, out_path, fpath=args.file, files_api=args.files_api)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    files: list[Path] = []
    if args.batch:
        files = [p for p in args.batch if p.exists()]
    elif args.batch_dir:
        if not args.batch_dir.is_dir():
            print(f"Error: not a directory: {args.batch_dir}", file=sys.stderr)
            sys.exit(1)
        files = sorted(args.batch_dir.glob("**/*.xml"))
    else:
        print("Provide one of: --text, --file, --batch, --batch-dir", file=sys.stderr)
        sys.exit(1)

    # Skip already-expanded files to avoid re-expanding
    files = [f for f in files if not f.stem.endswith("_expanded")]

    if not files:
        print("No XML files to process (excluding *_expanded.xml).", file=sys.stderr)
        return

    out_dir = args.out_dir
    parallel_files = max(1, min(16, getattr(args, "parallel_files", 1) or 1))

    def _is_timeout(e: BaseException) -> bool:
        if isinstance(e, TimeoutError):
            return True
        s = str(e).lower()
        return "timeout" in s or "timed out" in s

    def process_file(f: Path) -> tuple[Path, bool, str]:
        """Process one file, return (path, success, message). Retries on timeout."""
        xml = f.read_text(encoding="utf-8")
        out_path = (out_dir / f"{f.stem}_expanded.xml") if out_dir else (f.parent / f"{f.stem}_expanded.xml")
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                run(xml, out_path, fpath=f, files_api=args.files_api)
                return (f, True, f"OK: {f.name}")
            except Exception as e:
                if _is_timeout(e) and attempt < max_attempts - 1:
                    continue
                return (f, False, f"FAIL: {f.name}: {e}")

    if parallel_files <= 1:
        # Sequential
        for f in files:
            _, ok, msg = process_file(f)
            print(msg, file=sys.stderr)
    else:
        # Parallel files
        from concurrent.futures import ThreadPoolExecutor, as_completed
        print(f"Processing {len(files)} files ({parallel_files} in parallel)…", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=parallel_files) as executor:
            futures = {executor.submit(process_file, f): f for f in files}
            for future in as_completed(futures):
                _, ok, msg = future.result()
                print(msg, file=sys.stderr)


def _run_test_gemini(args: argparse.Namespace) -> None:
    from run_gemini import test_gemini_connection

    api_key = getattr(args, "api_key", None) or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    timeout = float(getattr(args, "timeout", 15) or 15)
    ok, msg = test_gemini_connection(api_key=api_key or None, timeout=timeout)
    print(msg, file=sys.stderr)
    if ok:
        print("OK", file=sys.stderr)
        return
    sys.exit(1)


def _run_eval(args: argparse.Namespace) -> None:
    """Run evaluation harness: rules-only, local (Ollama), Gemini; compare outputs and print report."""
    from .expander import expand_xml
    from .examples_io import load_examples

    corpus_files = args.corpus
    if not corpus_files:
        default_corpus = _PROJECT_ROOT / "demo_latin.xml"
        if not default_corpus.exists():
            print(f"Error: no --corpus given and {default_corpus} not found.", file=sys.stderr)
            sys.exit(1)
        corpus_files = [default_corpus]
    else:
        for p in corpus_files:
            if not p.exists():
                print(f"Error: corpus file not found: {p}", file=sys.stderr)
                sys.exit(1)

    examples_path = getattr(args, "examples", _PROJECT_ROOT / "examples.json")
    try:
        examples = load_examples(examples_path)
    except ValueError as e:
        print(f"Error loading examples: {e}", file=sys.stderr)
        sys.exit(1)

    out_dir = args.out_dir or (_PROJECT_ROOT / "dist" / "eval")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use first corpus file for eval (single-doc comparison)
    xml_content = corpus_files[0].read_text(encoding="utf-8")
    api_key = getattr(args, "api_key", None) or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    model_gemini = _env("GEMINI_MODEL", _DEFAULT_GEMINI)
    model_local = getattr(args, "local_model", "llama3.2")

    results: dict[str, str] = {}
    errors: dict[str, str] = {}

    # Rules-only
    try:
        results["rules"] = expand_xml(xml_content, examples, backend="rules")
        (out_dir / "rules.xml").write_text(results["rules"], encoding="utf-8")
        print("rules: OK", file=sys.stderr)
    except Exception as e:
        errors["rules"] = str(e)
        print(f"rules: FAIL — {e}", file=sys.stderr)

    # Local (Ollama)
    try:
        results["local"] = expand_xml(
            xml_content, examples, backend="local", model=model_local,
        )
        (out_dir / "local.xml").write_text(results["local"], encoding="utf-8")
        print("local (Ollama): OK", file=sys.stderr)
    except Exception as e:
        errors["local"] = str(e)
        print(f"local (Ollama): FAIL — {e}", file=sys.stderr)

    # Gemini (optional)
    if not getattr(args, "no_gemini", False) and api_key:
        try:
            results["gemini"] = expand_xml(
                xml_content, examples, model=model_gemini, api_key=api_key, backend="gemini",
            )
            (out_dir / "gemini.xml").write_text(results["gemini"], encoding="utf-8")
            print("gemini: OK", file=sys.stderr)
        except Exception as e:
            errors["gemini"] = str(e)
            print(f"gemini: FAIL — {e}", file=sys.stderr)
    else:
        print("gemini: skipped (--no-gemini or no API key)", file=sys.stderr)

    # Report
    print("", file=sys.stderr)
    print("--- Eval report ---", file=sys.stderr)
    backends = [b for b in ("rules", "local", "gemini") if b in results]
    if len(backends) < 2:
        print("Need at least two backends to compare.", file=sys.stderr)
        if errors:
            for b, err in errors.items():
                print(f"  {b}: {err}", file=sys.stderr)
        return

    for i, a in enumerate(backends):
        for b in backends[i + 1:]:
            sa, sb = results[a], results[b]
            if sa.strip() == sb.strip():
                print(f"  {a} vs {b}: identical", file=sys.stderr)
            else:
                print(f"  {a} vs {b}: differ", file=sys.stderr)
    print(f"Artifacts written to {out_dir}", file=sys.stderr)


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "train":
        ap = argparse.ArgumentParser(
            description="Add diplomatic → full example pairs (train locally).",
        )
        ap.add_argument(
            "--examples",
            type=Path,
            default=Path("examples.json"),
            help="Examples JSON path (default: examples.json)",
        )
        ap.add_argument("--list", "-l", action="store_true", help="List current pairs")
        ap.add_argument("--add", action="store_true", help="Add one pair via --diplomatic / --full")
        ap.add_argument("--diplomatic", "-d", type=str, help="Diplomatic text (with --add)")
        ap.add_argument("--full", "-f", type=str, help="Full form (with --add)")
        args = ap.parse_args(argv[1:])
        _run_train(args)
        return

    if argv and argv[0] == "test-gemini":
        ap = argparse.ArgumentParser(description="Test Gemini API connection. Print helpful error on failure.")
        ap.add_argument("--api-key", type=str, default=None, help="Gemini API key (else env / .env)")
        ap.add_argument("--timeout", type=float, default=15, help="Timeout seconds (default 15)")
        args = ap.parse_args(argv[1:])
        _run_test_gemini(args)
        return

    if argv and argv[0] == "eval":
        ap = argparse.ArgumentParser(
            description="Evaluation harness: compare rules-only, local (Ollama), and Gemini outputs.",
        )
        ap.add_argument(
            "--corpus",
            type=Path,
            nargs="*",
            default=None,
            help="Corpus XML file(s); default: demo_latin.xml in project root",
        )
        ap.add_argument(
            "--examples",
            type=Path,
            default=_PROJECT_ROOT / "examples.json",
            help="Examples JSON path (default: examples.json)",
        )
        ap.add_argument(
            "--out-dir",
            type=Path,
            default=None,
            help="Write artifacts here (default: dist/eval)",
        )
        ap.add_argument(
            "--no-gemini",
            action="store_true",
            help="Skip Gemini run (e.g. no API key or offline)",
        )
        ap.add_argument(
            "--api-key",
            type=str,
            default=None,
            help="Gemini API key (overrides env)",
        )
        ap.add_argument(
            "--local-model",
            type=str,
            default="llama3.2",
            help="Ollama model for local run (default: llama3.2)",
        )
        args = ap.parse_args(argv[1:])
        _run_eval(args)
        return

    expand_argv = argv[1:] if argv and argv[0] == "expand" else argv
    ap = argparse.ArgumentParser(
        description="Expand diplomatic transcriptions in XML (TEI) via Gemini or local Ollama.",
    )
    ap.add_argument("--text", type=str, help="Raw XML string to process")
    ap.add_argument("--file", type=Path, help="Single input XML file")
    ap.add_argument("--batch", type=Path, nargs="+", help="Batch: multiple XML files")
    ap.add_argument("--batch-dir", type=Path, help="Batch: all .xml files in directory")
    ap.add_argument(
        "--examples",
        type=Path,
        default=Path("examples.json"),
        help="Path to examples JSON (default: examples.json)",
    )
    ap.add_argument(
        "--model",
        type=str,
        default=_env("GEMINI_MODEL", _DEFAULT_GEMINI),
        help=f"Gemini model (default: GEMINI_MODEL or {_DEFAULT_GEMINI})",
    )
    ap.add_argument(
        "--backend",
        type=str,
        choices=("gemini", "local"),
        default="gemini",
        help="Backend: gemini (API) or local (Ollama)",
    )
    ap.add_argument(
        "--local-model",
        type=str,
        default="llama3.2",
        help="Ollama model when --backend local (default: llama3.2)",
    )
    ap.add_argument(
        "--modality",
        type=str,
        choices=("full", "conservative", "normalize", "aggressive", "local"),
        default="full",
        help="Expansion style: full (default), conservative, normalize, aggressive, local (for non-Gemini models)",
    )
    ap.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Gemini API key (overrides GEMINI_API_KEY / GOOGLE_API_KEY)",
    )
    ap.add_argument(
        "--prompt-key",
        action="store_true",
        help="Prompt for API key on stdin when missing (interactive)",
    )
    ap.add_argument(
        "--max-concurrent",
        type=int,
        default=None,
        metavar="N",
        help="Max parallel blocks (default: 4 gemini, 6 local; env EXPANDER_MAX_CONCURRENT)",
    )
    ap.add_argument(
        "--passes",
        type=int,
        default=1,
        metavar="N",
        help="Recursive correction passes (1-5, default 1)",
    )
    ap.add_argument("--out", type=Path, help="Output path (single file or --text)")
    ap.add_argument("--out-dir", type=Path, help="Output directory for batch")
    ap.add_argument(
        "--parallel-files",
        type=int,
        default=1,
        metavar="N",
        help="Process N files in parallel for batch (default 1 = sequential)",
    )
    ap.add_argument(
        "--files-api",
        action="store_true",
        help="Upload input file(s) via Gemini Files API and pass as context (--file / --batch only)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM; leave block text unchanged (pipeline test only)",
    )
    ap.add_argument(
        "--block-by-block",
        action="store_true",
        help="Expand each block separately (default)",
    )
    ap.add_argument(
        "--whole-doc",
        action="store_true",
        help="Expand entire document in one API call (instead of block-by-block)",
    )
    ap.add_argument(
        "--max-examples",
        type=int,
        default=None,
        metavar="N",
        help="Cap on examples injected per call (default: use all)",
    )
    ap.add_argument(
        "--example-strategy",
        type=str,
        choices=("longest-first", "most-recent"),
        default="longest-first",
        help="Which examples to use when capped (default: longest-first)",
    )
    ap.add_argument("--version", "-V", action="version", version=__import__("expand_diplomatic._version", fromlist=["__version__"]).__version__)
    args = ap.parse_args(expand_argv)
    _run_expand(args)


if __name__ == "__main__":
    main()
