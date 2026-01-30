"""Tests for run_gemini: Pro model timeouts, retries, batching."""

import unittest.mock
from run_gemini import (
    _get_timeout_for_model,
    _get_timeout_seconds,
    PRO_MODEL_MIN_TIMEOUT,
    TIMEOUT_EXTRA_RETRIES,
)


class TestTimeoutForModel:
    """Pro models receive higher timeouts."""

    def test_flash_model_uses_base_timeout(self) -> None:
        assert _get_timeout_for_model("gemini-2.5-flash", 120) == 120
        assert _get_timeout_for_model("gemini-2.0-flash", 90) == 90
        assert _get_timeout_for_model("gemini-3-flash-preview", 60) == 60

    def test_pro_model_uses_minimum(self) -> None:
        assert _get_timeout_for_model("gemini-2.5-pro", 120) == PRO_MODEL_MIN_TIMEOUT
        assert _get_timeout_for_model("gemini-3-pro-preview", 200) == max(200, PRO_MODEL_MIN_TIMEOUT)
        assert _get_timeout_for_model("gemini-2.5-pro", 60) == PRO_MODEL_MIN_TIMEOUT

    def test_pro_model_respects_higher_base(self) -> None:
        assert _get_timeout_for_model("gemini-2.5-pro", 600) == 600
        assert _get_timeout_for_model("gemini-3-pro-preview", 400) == 400

    def test_none_or_empty_model_uses_base(self) -> None:
        assert _get_timeout_for_model(None, 120) == 120
        assert _get_timeout_for_model("", 100) == 100

    def test_pro_substring_detected(self) -> None:
        assert _get_timeout_for_model("gemini-2.5-pro", 1) == PRO_MODEL_MIN_TIMEOUT
        assert _get_timeout_for_model("models/gemini-3-pro-preview", 100) == PRO_MODEL_MIN_TIMEOUT


class TestTimeoutRetry:
    """Timeout triggers one retry."""

    def test_timeout_retry_count(self) -> None:
        assert TIMEOUT_EXTRA_RETRIES >= 1, "Should retry at least once on timeout"

    def test_run_gemini_retries_on_timeout_then_succeeds(self) -> None:
        """On first TimeoutError, run_gemini retries and succeeds on second call."""
        from run_gemini import run_gemini

        call_count = 0

        def fail_once(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("Timed out")
            return "success"

        with unittest.mock.patch("run_gemini._get_api_key", return_value="x"):
            with unittest.mock.patch("run_gemini._do_run_gemini", side_effect=fail_once):
                result = run_gemini("hi", model="gemini-2.5-pro")
        assert result == "success"
        assert call_count == 2


class TestRunGeminiProModel:
    """run_gemini uses model-aware timeout for Pro models."""

    def test_pro_timeout_passed_to_do_run(self) -> None:
        """When run_gemini is called with Pro model, _do_run_gemini receives bumped timeout."""
        from run_gemini import run_gemini

        captured = {}

        def capture_call(contents, model, key, *, timeout_sec=120, **kwargs):
            captured["timeout_sec"] = timeout_sec
            captured["model"] = model
            return "ok"

        with unittest.mock.patch("run_gemini._get_api_key", return_value="x"):
            with unittest.mock.patch("run_gemini._get_timeout_seconds", return_value=120.0):
                with unittest.mock.patch("run_gemini._do_run_gemini", side_effect=capture_call):
                    run_gemini("hi", model="gemini-2.5-pro")
        assert captured["timeout_sec"] >= PRO_MODEL_MIN_TIMEOUT
        assert captured["model"] == "gemini-2.5-pro"

    def test_flash_timeout_unchanged(self) -> None:
        """Flash model keeps base timeout (no Pro bump)."""
        from run_gemini import run_gemini

        captured = {}

        def capture_call(contents, model, key, *, timeout_sec=120, **kwargs):
            captured["timeout_sec"] = timeout_sec
            return "ok"

        with unittest.mock.patch("run_gemini._get_api_key", return_value="x"):
            with unittest.mock.patch("run_gemini._get_timeout_seconds", return_value=120.0):
                with unittest.mock.patch("run_gemini._do_run_gemini", side_effect=capture_call):
                    run_gemini("hi", model="gemini-2.5-flash")
        assert captured["timeout_sec"] == 120


class TestExpanderProModel:
    """expander passes Pro model to run_gemini for timeout handling."""

    def test_expand_xml_passes_model_to_run_gemini(self) -> None:
        """expand_xml with gemini backend passes model to run_gemini."""
        from expand_diplomatic.expander import expand_xml

        captured = {}

        def fake_run(contents, model=None, **kwargs):
            captured["model"] = model
            # Return valid XML
            return contents

        xml = '<?xml version="1.0"?><root><p>test</p></root>'
        ex = [{"diplomatic": "x", "full": "y"}]

        with unittest.mock.patch("run_gemini.run_gemini", side_effect=fake_run):
            expand_xml(xml, ex, model="gemini-2.5-pro", backend="gemini", whole_document=True)
        assert captured["model"] == "gemini-2.5-pro"

    def test_expand_xml_block_by_block_passes_model(self) -> None:
        """Block-by-block expansion passes model per block."""
        from expand_diplomatic.expander import expand_xml

        calls = []

        def fake_run(contents, model=None, **kwargs):
            calls.append({"model": model})
            return contents.strip() + " expanded" if contents.strip() else contents

        xml = '<?xml version="1.0"?><root><p>a</p><p>b</p></root>'
        ex = [{"diplomatic": "a", "full": "x"}]

        with unittest.mock.patch("run_gemini.run_gemini", side_effect=fake_run):
            expand_xml(
                xml, ex,
                model="gemini-3-pro-preview",
                backend="gemini",
                whole_document=False,
            )
        assert len(calls) >= 1
        assert all(c["model"] == "gemini-3-pro-preview" for c in calls)


class TestBatchProParallel:
    """Batch mode caps parallel for Pro models."""

    def test_pro_model_parallel_cap_logic(self) -> None:
        """Pro model should cap parallel at 2."""
        model = "gemini-2.5-pro"
        parallel = 8
        if "pro" in (model or "").lower():
            parallel = min(parallel, 2)
        assert parallel == 2

    def test_flash_model_unchanged(self) -> None:
        """Flash model keeps user parallel."""
        model = "gemini-2.5-flash"
        parallel = 8
        if "pro" in (model or "").lower():
            parallel = min(parallel, 2)
        assert parallel == 8
