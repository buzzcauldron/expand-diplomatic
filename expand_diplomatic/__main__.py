"""CLI for expand_diplomatic: expand, train (add examples locally)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

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
    use_files_api: bool = False,
    dry_run: bool = False,
    max_concurrent: int | None = None,
    passes: int = 1,
) -> None:
    from .expander import expand_xml

    input_path = input_file_path if use_files_api and backend == "gemini" else None
    result = expand_xml(
        xml_content,
        examples,
        model=model,
        api_key=api_key,
        input_file_path=input_path,
        dry_run=dry_run,
        backend=backend,
        modality=modality,
        max_concurrent=max_concurrent,
        passes=passes,
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
            use_files_api=files_api,
            dry_run=dry_run,
            max_concurrent=mc,
            passes=passes,
        )

    if args.text is not None:
        run(args.text, args.out)
        return

    if args.file is not None:
        if not args.file.exists():
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        xml = args.file.read_text(encoding="utf-8")
        out_path = args.out or (args.file.parent / f"{args.file.stem}_expanded.xml")
        run(xml, out_path, fpath=args.file, files_api=args.files_api)
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

    if not files:
        print("No XML files to process.", file=sys.stderr)
        return

    out_dir = args.out_dir
    for f in files:
        xml = f.read_text(encoding="utf-8")
        out_path = (out_dir / f"{f.stem}_expanded.xml") if out_dir else (f.parent / f"{f.stem}_expanded.xml")
        run(xml, out_path, fpath=f, files_api=args.files_api)


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
        default=_env("GEMINI_MODEL", "gemini-2.5-flash"),
        help="Gemini model (default: GEMINI_MODEL or gemini-2.5-flash)",
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
        "--files-api",
        action="store_true",
        help="Upload input file(s) via Gemini Files API and pass as context (--file / --batch only)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM; leave block text unchanged (pipeline test only)",
    )
    ap.add_argument("--version", "-V", action="version", version=__import__("expand_diplomatic._version", fromlist=["__version__"]).__version__)
    args = ap.parse_args(expand_argv)
    _run_expand(args)


if __name__ == "__main__":
    main()
