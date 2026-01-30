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
import concurrent.futures
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

# Extra retries for 429 with longer backoff (seconds)
_429_BACKOFF_SEC = 8
_429_EXTRA_RETRIES = 2

from dotenv import load_dotenv
from google import genai
from google.genai import types

try:
    from google.genai import errors as genai_errors
except ImportError:
    genai_errors = None  # type: ignore[assignment]

# Load .env from project root (store secrets there; never commit .env)
load_dotenv(Path(__file__).resolve().parent / ".env")

DEFAULT_TIMEOUT = 120
DEFAULT_RETRY_ATTEMPTS = 2


def _get_timeout_seconds() -> float:
    v = os.environ.get("GEMINI_TIMEOUT", "")
    if not v:
        return float(DEFAULT_TIMEOUT)
    try:
        return max(10.0, float(v))
    except ValueError:
        return float(DEFAULT_TIMEOUT)


def _get_retry_attempts() -> int:
    v = os.environ.get("GEMINI_RETRY_ATTEMPTS", "")
    if not v:
        return DEFAULT_RETRY_ATTEMPTS
    try:
        return max(0, int(v))
    except ValueError:
        return DEFAULT_RETRY_ATTEMPTS


def _http_options(timeout_sec: float, retry_attempts: int) -> types.HttpOptions:
    """Build HttpOptions with timeout and optional retries for Gemini Client.
    HttpOptions.timeout is in milliseconds; we use seconds, so multiply by 1000.
    """
    timeout_ms = max(10_000, int(timeout_sec * 1000))
    opts: dict[str, Any] = {"timeout": timeout_ms}
    if retry_attempts > 0:
        opts["retry_options"] = types.HttpRetryOptions(
            attempts=retry_attempts,
            initial_delay=1.0,
        )
    return types.HttpOptions(**opts)


def _get_api_key(api_key: Optional[str]) -> str:
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY (or pass api_key)")
    return key


def prepare_file_session(
    file_path: str | Path,
    api_key: Optional[str] = None,
    *,
    timeout: Optional[float] = None,
) -> tuple[Any, Any]:
    """
    Create a client, upload the file via the Files API, and return (client, uploaded_file).
    Use these with run_gemini(..., client=..., uploaded_file=...) for multiple calls.
    Caller must close the client when done (or use close_file_session).
    timeout: seconds for client requests (default GEMINI_TIMEOUT). Applies to upload and later generate_content.
    """
    key = _get_api_key(api_key)
    t = timeout if timeout is not None else _get_timeout_seconds()
    client = genai.Client(
        api_key=key,
        http_options=_http_options(t, _get_retry_attempts()),
    )
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


def _do_run_gemini(
    contents: str,
    model: str,
    key: str,
    *,
    timeout_sec: float = 120.0,
    retry_attempts: int = 2,
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    max_output_tokens: int = 8192,
    file_path: Optional[str | Path] = None,
    client: Optional[Any] = None,
    uploaded_file: Optional[Any] = None,
) -> str:
    own_client = client is None
    if own_client:
        client = genai.Client(
            api_key=key,
            http_options=_http_options(timeout_sec, retry_attempts),
        )

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


def run_gemini(
    contents: str,
    model: str = "gemini-2.5-flash",
    api_key: Optional[str] = None,
    *,
    system_instruction: Optional[str] = None,
    temperature: float = 0.2,
    max_output_tokens: int = 8192,
    file_path: Optional[str | Path] = None,
    client: Optional[Any] = None,
    uploaded_file: Optional[Any] = None,
    timeout: Optional[float] = None,
) -> str:
    """
    Send contents to Gemini and return the generated text.

    api_key: from GEMINI_API_KEY or GOOGLE_API_KEY if not given.
    system_instruction: optional system prompt (ideasrule-style).
    file_path: upload this file via Files API and prepend to contents (optional).
    client, uploaded_file: reuse existing client and uploaded file (no extra upload).
    timeout: seconds to wait per request (default: GEMINI_TIMEOUT env or 120).
      If the request takes longer, raises TimeoutError.
    """
    key = _get_api_key(api_key)
    t = timeout if timeout is not None else _get_timeout_seconds()
    retries = _get_retry_attempts()
    # Thread timeout slightly above HTTP timeout so HTTP timeout fires first when respected
    thread_timeout = t + 15.0

    def do_call() -> str:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(
                _do_run_gemini,
                contents,
                model,
                key,
                timeout_sec=t,
                retry_attempts=retries,
                system_instruction=system_instruction,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                file_path=file_path,
                client=client,
                uploaded_file=uploaded_file,
            )
            try:
                return fut.result(timeout=thread_timeout)
            except concurrent.futures.TimeoutError:
                raise TimeoutError(
                    f"Gemini API request timed out (limit {t:.0f}s). "
                    "Set GEMINI_TIMEOUT (seconds) in .env to change, or use backend=local."
                ) from None

    last_err: Optional[Exception] = None
    for attempt in range(1 + _429_EXTRA_RETRIES):
        try:
            return do_call()
        except Exception as e:
            last_err = e
            if genai_errors and isinstance(e, genai_errors.APIError):
                code = getattr(e, "code", 0) or 0
                if code == 429 and attempt < _429_EXTRA_RETRIES:
                    time.sleep(_429_BACKOFF_SEC)
                    continue
            raise
    raise last_err or RuntimeError("Unexpected")


def _api_error_message(code: int, status: str | None, message: str | None) -> str:
    """Turn Gemini API error code/status/message into a short, actionable message."""
    status = status or ""
    message = (message or "").strip()
    hint = "https://aistudio.google.com/apikey"
    if code == 400:
        low = (message or "").lower()
        if "api key" in low and ("invalid" in low or "not valid" in low or "missing" in low):
            return (
                f"Invalid or missing API key (400). {message}\n"
                "Set GEMINI_API_KEY or GOOGLE_API_KEY in .env or environment. Get a key: https://aistudio.google.com/apikey"
            )
        return (
            f"Bad request (400). {message}\n"
            "Check your request format. If billing is required, enable it in Google Cloud."
        )
    if code == 401:
        return (
            f"Invalid or missing API key (401). {message}\n"
            f"Set GEMINI_API_KEY or GOOGLE_API_KEY in .env or environment. Get a key: {hint}"
        )
    if code == 403:
        return (
            f"Permission denied (403). {message}\n"
            f"Key may lack access or be restricted. Check {hint}"
        )
    if code == 404:
        return f"Not found (404). {message}\nModel or resource may be unavailable."
    if code == 429:
        return (
            "Rate limit exceeded (429). Too many requests—free tier has strict limits.\n\n"
            "• Lower Parallel to 1 in the toolbar (fewer concurrent API calls)\n"
            "• Wait 1–2 minutes and retry\n"
            "• Use 'Use local model' to avoid API limits (Ollama or rules-based)\n"
            "• See: https://ai.google.dev/gemini-api/docs/errors#429"
        )
    if code == 500:
        return f"Server error (500). {message}\nRetry later or try a different model."
    if code == 503:
        return f"Service unavailable (503). {message}\nRetry in a few moments."
    if code >= 400:
        return f"API error {code} {status}. {message or '(no details)'}"
    return message or f"API error {code}"


def format_api_error(exc: Exception) -> str:
    """Convert API exception to a user-friendly message."""
    if genai_errors and isinstance(exc, genai_errors.APIError):
        code = getattr(exc, "code", 0) or 0
        status = getattr(exc, "status", None)
        msg = getattr(exc, "message", None) or str(exc)
        return _api_error_message(code, status, msg)
    s = str(exc).strip()
    # Parse "429 RESOURCE_EXHAUSTED" or similar from raw string
    if "429" in s or "RESOURCE_EXHAUSTED" in s:
        return _api_error_message(429, "RESOURCE_EXHAUSTED", "Resource exhausted. Please try again later.")
    if "400" in s and ("invalid" in s.lower() or "api key" in s.lower()):
        return _api_error_message(400, "INVALID_ARGUMENT", s)
    if "401" in s:
        return _api_error_message(401, "UNAUTHENTICATED", s)
    if "403" in s:
        return _api_error_message(403, "PERMISSION_DENIED", s)
    if "503" in s:
        return _api_error_message(503, "UNAVAILABLE", s)
    if "timeout" in s.lower() or "timed out" in s.lower():
        return f"{s}\n\nSet GEMINI_TIMEOUT in .env or use backend=local."
    return s


def test_gemini_connection(
    api_key: Optional[str] = None,
    timeout: float = 15.0,
) -> tuple[bool, str]:
    """
    Test Gemini API connection with a minimal request.
    Returns (success, message). On failure, message is a helpful error with code and next steps.
    """
    try:
        key = _get_api_key(api_key)
    except RuntimeError as e:
        return (
            False,
            "No API key set.\n"
            "Set GEMINI_API_KEY or GOOGLE_API_KEY in .env or environment.\n"
            "Get a key: https://aistudio.google.com/apikey",
        )

    try:
        run_gemini("Reply with exactly: OK", model="gemini-2.5-flash", api_key=key, timeout=timeout)
        return (True, "Connection OK. Gemini responded successfully.")
    except TimeoutError:
        return (
            False,
            f"Connection timed out (limit {timeout:.0f}s).\n"
            "Check your network. Increase GEMINI_TIMEOUT in .env if needed, or use backend=local.",
        )
    except Exception as e:  # noqa: BLE001
        if genai_errors and isinstance(e, genai_errors.APIError):
            code = getattr(e, "code", 0) or 0
            status = getattr(e, "status", None)
            msg = getattr(e, "message", None) or str(e)
            return (False, _api_error_message(code, status, msg))
        err = str(e).strip()
        if "GEMINI_API_KEY" in err or "GOOGLE_API_KEY" in err or "api key" in err.lower():
            return (
                False,
                "No API key set.\n"
                "Set GEMINI_API_KEY or GOOGLE_API_KEY in .env or environment.\n"
                "Get a key: https://aistudio.google.com/apikey",
            )
        if "timeout" in err.lower() or "timed out" in err.lower():
            return (
                False,
                f"Connection timed out (limit {timeout:.0f}s).\n"
                "Check your network or use backend=local.",
            )
        if "connection" in err.lower() or "network" in err.lower() or "urllib" in str(type(e)):
            return (
                False,
                "Network error. Check your internet connection and firewall.",
            )
        return (False, f"Unexpected error: {err}")


def _main() -> None:
    ap = argparse.ArgumentParser(description="Call Gemini API for text generation.")
    ap.add_argument("--prompt", "-p", required=True, help="Input prompt")
    ap.add_argument("--model", "-m", default="gemini-2.5-flash", help="Gemini model")
    ap.add_argument("--temperature", "-t", type=float, default=0.2, help="Temperature")
    ap.add_argument("--file", "-f", type=Path, help="Upload file via Files API and send with prompt")
    ap.add_argument("--timeout", type=float, default=None, help="Request timeout seconds (default: GEMINI_TIMEOUT or 120)")
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
            timeout=args.timeout,
        )
        print(out)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _main()
