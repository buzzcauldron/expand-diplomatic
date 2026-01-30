"""
Call Gemini API for text generation.

Uses the same pattern as ideasrule/latin_documents run_gemini:
  google.genai Client, generate_content, GenerateContentConfig.

Supports the Files API (https://ai.google.dev/api/files): optionally upload
a file and pass it in contents so Gemini can use it as context.

Module: run_gemini(contents, model=..., file_path=..., ...) -> str
        prepare_file_session(file_path, api_key) -> (client, uploaded_file)
CLI:    python run_gemini.py --prompt "..." [--model MODEL] [--file PATH]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load .env from project root (store secrets there; never commit .env)
load_dotenv(Path(__file__).resolve().parent / ".env")


def _get_api_key(api_key: Optional[str]) -> str:
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY (or pass api_key)")
    return key


def prepare_file_session(
    file_path: str | Path,
    api_key: Optional[str] = None,
) -> tuple[Any, Any]:
    """
    Create a client, upload the file via the Files API, and return (client, uploaded_file).
    Use these with run_gemini(..., client=..., uploaded_file=...) for multiple calls.
    Caller must close the client when done (or use close_file_session).
    """
    key = _get_api_key(api_key)
    client = genai.Client(api_key=key)
    uploaded = client.files.upload(file=Path(file_path))
    return (client, uploaded)


def close_file_session(client: Any, uploaded_file: Any, delete: bool = True) -> None:
    """Close the client and optionally delete the uploaded file."""
    if delete and uploaded_file is not None and getattr(uploaded_file, "name", None):
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass
    client.close()


def run_gemini(
    contents: str,
    model: str = "gemini-2.5-pro",
    api_key: Optional[str] = None,
    *,
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    max_output_tokens: int = 8192,
    file_path: Optional[str | Path] = None,
    client: Optional[Any] = None,
    uploaded_file: Optional[Any] = None,
) -> str:
    """
    Send contents to Gemini and return the generated text.

    api_key: from GEMINI_API_KEY or GOOGLE_API_KEY if not given.
    system_instruction: optional system prompt (ideasrule-style).
    file_path: upload this file via Files API and prepend to contents (optional).
    client, uploaded_file: reuse existing client and uploaded file (no extra upload).
    """
    key = _get_api_key(api_key)
    own_client = client is None
    if own_client:
        client = genai.Client(api_key=key)

    do_upload = uploaded_file is None and file_path is not None
    if do_upload:
        uploaded_file = client.files.upload(file=Path(file_path))

    config_kw: dict = {"temperature": temperature, "max_output_tokens": max_output_tokens}
    if system_instruction is not None:
        config_kw["system_instruction"] = system_instruction
    config = types.GenerateContentConfig(**config_kw)

    if uploaded_file is not None:
        payload: Any = [uploaded_file, "\n\n", contents]
    else:
        payload = contents

    response = client.models.generate_content(
        model=model,
        config=config,
        contents=payload,
    )
    out = (response.text or "").strip()
    if own_client:
        client.close()
    return out


def _main() -> None:
    ap = argparse.ArgumentParser(description="Call Gemini API for text generation.")
    ap.add_argument("--prompt", "-p", required=True, help="Input prompt")
    ap.add_argument("--model", "-m", default="gemini-2.5-pro", help="Gemini model")
    ap.add_argument("--temperature", "-t", type=float, default=0.2, help="Temperature")
    ap.add_argument("--file", "-f", type=Path, help="Upload file via Files API and send with prompt")
    args = ap.parse_args()

    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
        print("Error: set GEMINI_API_KEY or GOOGLE_API_KEY", file=sys.stderr)
        sys.exit(1)

    try:
        out = run_gemini(
            args.prompt,
            model=args.model,
            temperature=args.temperature,
            file_path=args.file,
        )
        print(out)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _main()
