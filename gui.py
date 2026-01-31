#!/usr/bin/env python3
"""
Minimal GUI for expand_diplomatic: input/output panels, Load / Expand / Save, train examples.
Requires tkinter (stdlib). Run: python gui.py
"""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk

from dotenv import load_dotenv, set_key

ROOT_DIR = Path(__file__).resolve().parent
ENV_PATH = ROOT_DIR / ".env"
ENV_EXAMPLE = ROOT_DIR / ".env.example"


def _config_dir() -> Path:
    """Config directory: APPDATA on Windows, .config in home elsewhere."""
    if os.name == "nt":
        base = os.environ.get("APPDATA", "").strip()
        if not base:
            base = str(Path.home())
        return Path(base) / "expand_diplomatic"
    return Path.home() / ".config" / "expand_diplomatic"


PREFS_PATH = _config_dir() / "preferences.json"


def _ensure_env() -> None:
    """Create .env from .env.example if missing; then load .env."""
    if not ENV_PATH.exists() and ENV_EXAMPLE.exists():
        import shutil

        shutil.copy(ENV_EXAMPLE, ENV_PATH)
    load_dotenv(ENV_PATH)


_ensure_env()


def _load_preferences() -> dict:
    """Load user preferences from disk. Returns dict; empty on failure."""
    import json
    try:
        if PREFS_PATH.exists():
            data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_preferences(prefs: dict) -> None:
    """Save user preferences to disk."""
    import json
    try:
        PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFS_PATH.write_text(json.dumps(prefs, indent=0), encoding="utf-8")
    except Exception:
        pass


# Lightweight imports at startup (no run_gemini, lxml); expand_xml lazy-loaded on first Expand
# ideasrule-style: defer heavy work; use fallback for fast startup
from expand_diplomatic.examples_io import add_learned_pairs, get_learned_path, load_examples, save_examples
from expand_diplomatic.gemini_models import DEFAULT_MODEL, FALLBACK_MODELS, format_model_with_speed

DEFAULT_EXAMPLES = ROOT_DIR / "examples.json"
BACKENDS = ("gemini", "local")
MODALITIES = ("full", "conservative", "normalize", "aggressive", "local")

# Use fallback models for instant startup; refresh from API in background
GEMINI_MODELS = FALLBACK_MODELS
DEFAULT_GEMINI_MODEL = DEFAULT_MODEL


def _add_tooltip(widget: tk.Widget, text: str, delay_ms: int = 500) -> None:
    """Show text in a tooltip when hovering over widget."""
    tip = [None]  # mutable ref for closure
    after_id = [None]

    def show(event: tk.Event) -> None:
        def show_after() -> None:
            after_id[0] = None
            if tip[0] is not None:
                return
            tw = tk.Toplevel(widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
            lb = tk.Label(tw, text=text, justify=tk.LEFT, relief=tk.SOLID, borderwidth=1, background="#ffffc0", font=("", 9), padx=4, pady=2)
            lb.pack()
            tip[0] = tw

        after_id[0] = widget.after(delay_ms, show_after)

    def hide(event: tk.Event) -> None:
        if after_id[0] is not None:
            widget.after_cancel(after_id[0])
            after_id[0] = None
        if tip[0] is not None:
            tip[0].destroy()
            tip[0] = None

    widget.bind("<Enter>", show)
    widget.bind("<Leave>", hide)


def _apply_model_menu_labels(option_menu: tk.OptionMenu, var: tk.StringVar, models: tuple[str, ...]) -> None:
    """Rebuild option menu with speed tick marks (more · = faster)."""
    menu = option_menu["menu"]
    menu.delete(0, "end")
    for m in models:
        menu.add_command(label=format_model_with_speed(m), command=lambda v=m: var.set(v))


def _status(app: "App", msg: str) -> None:
    app.status_var.set(msg)
    app.root.update_idletasks()


def _resolve_api_key(app: "App") -> str | None:
    return app.session_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _update_processing_indicator(app: "App") -> None:
    """Update simple processing animation indicator."""
    if not getattr(app, "expand_running", False):
        return
    # Cycle through animation frames
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    current = getattr(app, "_processing_frame", 0)
    app._processing_frame = (current + 1) % len(frames)
    # Update status with animation
    base_status = getattr(app, "_base_status", "Processing…")
    _status(app, f"{frames[app._processing_frame]} {base_status}")
    # Schedule next frame
    app.root.after(80, lambda: _update_processing_indicator(app))


def _schedule_auto_learn(
    app: "App",
    xml_input: str,
    xml_output: str,
    examples_path: Path,
    *,
    model: str | None = None,
) -> None:
    """Run auto-learn in a background thread when Learn is ticked and Gemini was used.
    Aggressive training (GPU): higher cap. Huge weight on local pairs: main examples
    (examples.json) are never overwritten by Gemini guesses."""
    high_end = getattr(app, "_high_end_gpu", False)

    def learn() -> None:
        try:
            from expand_diplomatic.examples_io import DEFAULT_MAX_LEARNED

            from expand_diplomatic.expander import extract_expansion_pairs

            pairs = extract_expansion_pairs(xml_input, xml_output)
            if not pairs:
                return
            # Local pairs (main examples) have huge weight: never overwrite with Gemini guesses
            main_examples = load_examples(examples_path)
            local_diplomatic = {e.get("diplomatic", "").strip() for e in main_examples if e.get("diplomatic")}
            learned_path = get_learned_path(examples_path)
            add_learned_pairs(
                pairs,
                learned_path,
                max_learned=4000 if high_end else DEFAULT_MAX_LEARNED,
                model=model,
                local_diplomatic=local_diplomatic,
            )
        except Exception:
            pass  # Quiet: do not disturb user

    t = threading.Thread(target=learn, daemon=True)
    t.start()


def _expand_worker(
    xml: str,
    examples: list,
    api_key: str | None,
    app: "App",
    backend: str,
    model: str,
    modality: str,
    max_concurrent: int,
    passes: int = 1,
    run_id: int = 0,
) -> None:
    from expand_diplomatic.expander import ExpandCancelled, expand_xml

    def cancel_check() -> bool:
        return getattr(app, "cancel_requested", False)

    # Hang detection: track time since last progress update
    last_progress_time = [time.time()]
    HANG_THRESHOLD_SEC = 90  # Warn if no progress for this long

    def progress_cb(current: int, total: int, _msg: str) -> None:
        last_progress_time[0] = time.time()
        s = _msg if (total == 1 and _msg) else (f"block {current}/{total}" if total > 0 else "Processing…")
        pct = int(100 * current / total) if total > 0 else 0

        def update_ui() -> None:
            app.last_progress_time = time.time()
            app._base_status = s
            # Whole-doc uses indeterminate bar (animating); only set value for block-by-block
            if total > 1:
                app.progress_bar.configure(mode="determinate")
                app.progress_bar["value"] = pct
            # Show elapsed time
            elapsed = int(time.time() - app.expand_start_time)
            app.time_label_var.set(f"{elapsed}s")

        app.root.after(0, update_ui)

    def partial_cb(xml_result: str) -> None:
        """Display each completed block. If user had a block highlighted (double-click), stay there."""
        def update_output() -> None:
            out = app.output_txt
            # If user has synced block, preserve scroll and re-apply highlight after update
            block_idx = getattr(app, "_synced_block_idx", None)
            if block_idx is None:
                # Fallback: get block from paired/sel tag
                for tag in ("paired", "sel"):
                    rng = list(out.tag_ranges(tag))
                    if rng:
                        try:
                            pos = str(rng[0])
                            off = out.count("1.0", pos, "chars")[0]
                            content = out.get("1.0", tk.END)
                            ranges = app._get_block_ranges_cached(content)
                            for i, (s, e) in enumerate(ranges):
                                if s <= off < e:
                                    block_idx = i
                                    break
                        except Exception:
                            pass
                        break
            try:
                scroll_pos = out.yview()
            except Exception:
                scroll_pos = None
            out.delete("1.0", tk.END)
            out.insert("1.0", xml_result)
            if scroll_pos is not None:
                try:
                    out.yview_moveto(scroll_pos[0])
                except Exception:
                    pass
            if block_idx is not None:
                try:
                    ranges = app._get_block_ranges_cached(xml_result)
                    if block_idx < len(ranges):
                        s, e = ranges[block_idx]
                        start_idx = out.index(f"1.0 + {s} chars")
                        end_idx = out.index(f"1.0 + {e} chars")
                        out.tag_remove("paired", "1.0", tk.END)
                        out.tag_add("paired", start_idx, end_idx)
                except Exception:
                    pass
        app.root.after(0, update_output)

    whole_doc = app.whole_document_var.get() if getattr(app, "whole_document_var", None) else False
    ex_path = None
    if whole_doc and backend == "gemini" and not getattr(app, "_expand_include_learned", True):
        ex_path = getattr(app, "_expand_examples_path", None)

    result: str | None = None
    err: Exception | None = None
    try:
        result = expand_xml(
            xml,
            examples,
            api_key=api_key or None,
            backend=backend,
            model=model,
            modality=modality,
            progress_callback=progress_cb,
            partial_result_callback=partial_cb,
            max_concurrent=max_concurrent,
            passes=passes,
            cancel_check=cancel_check,
            whole_document=whole_doc,
            examples_path=ex_path,
        )
    except Exception as e:
        err = e

    def on_done() -> None:
        from run_gemini import format_api_error
        app.expand_btn.config(state=tk.NORMAL, text="Expand")
        try:
            app.progress_bar.stop()
        except Exception:
            pass
        app.progress_bar.configure(mode="determinate")
        app.progress_bar["value"] = 0
        app.time_label_var.set("")
        app.cancel_btn.config(state=tk.DISABLED)
        _stop_hang_check(app)
        if getattr(app, "expand_run_id", -1) != run_id:
            return
        if err is not None:
            if isinstance(err, ExpandCancelled):
                if getattr(app, "_restart_with_block_by_block", False):
                    app._restart_with_block_by_block = False
                    _status(app, "Switching to block-by-block…")
                    app.root.after(50, lambda: _run_expand_internal(
                        app,
                        app.last_expand_xml or "",
                        app.last_expand_api_key,
                        app.last_expand_backend,
                    ))
                else:
                    _status(app, "Cancelled.")
                    app.root.after(100, lambda: app._process_next_in_queue())
                return
            _status(app, "Idle")
            msg = format_api_error(err) if err else "Unknown error"
            _show_api_error_dialog(app, msg, xml, is_retry=True)
            # Process next in queue even on error
            app.root.after(100, lambda: app._process_next_in_queue())
            return
        out = app.output_txt
        block_idx = getattr(app, "_synced_block_idx", None)
        if block_idx is None:
            for tag in ("paired", "sel"):
                rng = list(out.tag_ranges(tag))
                if rng:
                    try:
                        pos = str(rng[0])
                        off = out.count("1.0", pos, "chars")[0]
                        content = out.get("1.0", tk.END)
                        ranges = app._get_block_ranges_cached(content)
                        for i, (s, e) in enumerate(ranges):
                            if s <= off < e:
                                block_idx = i
                                break
                    except Exception:
                        pass
                    break
        try:
            scroll_pos = out.yview()
        except Exception:
            scroll_pos = None
        out.delete("1.0", tk.END)
        out.insert("1.0", result or "")
        if getattr(app, "last_input_path", None) is not None:
            app.last_output_path = app.last_input_path.parent / f"{app.last_input_path.stem}_expanded.xml"
        if scroll_pos is not None:
            try:
                out.yview_moveto(scroll_pos[0])
            except Exception:
                pass
        if block_idx is not None:
            try:
                ranges = app._get_block_ranges_cached(result or "")
                if block_idx < len(ranges):
                    s, e = ranges[block_idx]
                    start_idx = out.index(f"1.0 + {s} chars")
                    end_idx = out.index(f"1.0 + {e} chars")
                    out.tag_remove("paired", "1.0", tk.END)
                    out.tag_add("paired", start_idx, end_idx)
            except Exception:
                pass
        
        elapsed = int(time.time() - app.expand_start_time)
        _status(app, f"Done in {elapsed}s.")
        # Auto-learn: quietly train local model on Gemini results in background
        if backend == "gemini" and getattr(app, "auto_learn_var", None) and app.auto_learn_var.get():
            ex_path = Path(app.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
            _schedule_auto_learn(app, xml, result or "", ex_path, model=model)
        
        # Process next item in queue if any
        app.root.after(100, lambda: app._process_next_in_queue())

    app.root.after(0, on_done)


def _start_hang_check(app: "App") -> None:
    """Start periodic hang check during expansion."""
    HANG_THRESHOLD_SEC = 90
    WHOLE_DOC_HANG_SEC = 330  # Whole-doc: single API call, Pro models timeout at 300s
    CHECK_INTERVAL_MS = 5000  # Check every 5s

    def check() -> None:
        if not app.expand_running:
            return
        elapsed_since_progress = time.time() - app.last_progress_time
        total_elapsed = int(time.time() - app.expand_start_time)
        # Update elapsed time display (keeps whole-doc timer ticking)
        app.time_label_var.set(f"{total_elapsed}s")
        threshold = WHOLE_DOC_HANG_SEC if getattr(app, "_expand_whole_doc", False) else HANG_THRESHOLD_SEC
        if elapsed_since_progress > threshold:
            app.status_var.set(f"⚠ Possible hang ({int(elapsed_since_progress)}s no progress)…")
        # Schedule next check
        app.hang_check_id = app.root.after(CHECK_INTERVAL_MS, check)

    app.hang_check_id = app.root.after(CHECK_INTERVAL_MS, check)


def _stop_hang_check(app: "App") -> None:
    """Stop hang check timer."""
    if app.hang_check_id is not None:
        try:
            app.root.after_cancel(app.hang_check_id)
        except Exception:
            pass
        app.hang_check_id = None
    app.expand_running = False


def _focus_main(app: "App") -> None:
    """Focus and raise main window (e.g. after closing modal dialogs)."""
    try:
        app.root.focus_set()
        app.root.lift()
    except Exception:
        pass


def _show_api_key_dialog(
    app: "App",
    title: str = "Enter API key",
    message: str = "Paste your Gemini API key (https://aistudio.google.com/apikey):",
    on_ok=None,
) -> None:
    """Toplevel: key Entry, 'Save to .env' checkbox, OK/Cancel. on_ok(key, save) called on OK."""
    win = tk.Toplevel(app.root)
    win.title(title)
    win.transient(app.root)
    win.grab_set()
    f = tk.Frame(win, padx=12, pady=12)
    f.pack(fill=tk.BOTH, expand=True)
    tk.Label(f, text=message, wraplength=400).pack(anchor=tk.W)
    var = tk.StringVar()
    e = tk.Entry(f, textvariable=var, width=48, show="*")
    e.pack(fill=tk.X, pady=(4, 8))
    save_var = tk.BooleanVar(value=True)
    tk.Checkbutton(f, text="Save to .env (project root)", variable=save_var).pack(anchor=tk.W)
    btns = tk.Frame(f)
    btns.pack(fill=tk.X, pady=(8, 0))

    def _close_key_dialog() -> None:
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        app.root.after(50, _focus_main, app)

    def ok() -> None:
        key = var.get().strip()
        if not key:
            messagebox.showwarning("API key", "Enter an API key.", parent=win)
            return
        save = save_var.get()
        if save:
            try:
                set_key(ENV_PATH, "GEMINI_API_KEY", key)
            except Exception as ex:
                messagebox.showerror("Save .env", str(ex), parent=win)
                return
            load_dotenv(ENV_PATH)
        if callable(on_ok):
            on_ok(key, save)
        _close_key_dialog()

    def cancel() -> None:
        app.expand_btn.config(state=tk.NORMAL)
        _close_key_dialog()

    tk.Button(btns, text="OK", command=ok).pack(side=tk.LEFT, padx=(0, 4))
    tk.Button(btns, text="Cancel", command=cancel).pack(side=tk.LEFT)
    win.geometry("+%d+%d" % (app.root.winfo_rootx() + 60, app.root.winfo_rooty() + 80))
    e.focus_set()
    win.protocol("WM_DELETE_WINDOW", cancel)


def _close_error_dialog(win: tk.Toplevel, app: "App", focus_main: bool = True) -> None:
    try:
        win.grab_release()
    except Exception:
        pass
    win.destroy()
    if focus_main:
        app.root.after(50, _focus_main, app)


def _show_api_error_dialog(
    app: "App",
    message: str,
    xml: str,
    *,
    is_retry: bool = False,
) -> None:
    """Offer: Enter API key | Use local model | Use online Gemini | Cancel.
    If is_retry and we had a key/backend, first ask 'Retry with same setup?' Yes/No; if No, show this.
    Retry always reloads examples from disk (retrain)."""
    key_used = getattr(app, "last_expand_api_key", None)
    backend_used = getattr(app, "last_expand_backend", "gemini")
    can_retry_same = is_retry and (key_used is not None or backend_used == "local")

    if can_retry_same and messagebox.askyesno(
        "Expand failed",
        "Expand failed:\n\n%s\n\nRetry with same setup? (Examples will be reloaded from disk.)" % message,
    ):
        app.backend = app.last_expand_backend
        app.backend_var.set(app.last_expand_backend)
        app._on_backend_change(app.last_expand_backend)
        _focus_main(app)
        _run_expand_internal(
            app, xml,
            app.last_expand_api_key,
            app.last_expand_backend,
            retry=True,
        )
        return

    def run_with_key(key: str, _save: bool) -> None:
        app.session_api_key = key
        app.backend = "gemini"
        app.backend_var.set("gemini")
        app._on_backend_change("gemini")
        _run_expand_internal(app, xml, key, "gemini", retry=True)

    win = tk.Toplevel(app.root)
    win.title("Expand failed" if is_retry else "No API key")
    win.transient(app.root)
    win.grab_set()
    f = tk.Frame(win, padx=12, pady=12)
    f.pack(fill=tk.BOTH, expand=True)
    prompt = "Expand failed:\n\n%s\n\nWhat do you want to do?" % message if is_retry else "No API key set.\n\nWhat do you want to do?"
    tk.Label(f, text=prompt, wraplength=420, justify=tk.LEFT).pack(anchor=tk.W)

    def enter_key() -> None:
        _close_error_dialog(win, app, focus_main=False)
        _show_api_key_dialog(
            app,
            title="Enter API key",
            message="Paste your Gemini API key (https://aistudio.google.com/apikey):",
            on_ok=lambda k, s: run_with_key(k, s),
        )

    def use_local() -> None:
        _close_error_dialog(win, app, focus_main=False)
        _focus_main(app)
        app.backend = "local"
        app.backend_var.set("local")
        app._on_backend_change("local")
        _run_expand_internal(app, xml, None, "local", retry=True)

    def use_online() -> None:
        _close_error_dialog(win, app, focus_main=False)
        _focus_main(app)
        app.backend = "gemini"
        app.backend_var.set("gemini")
        app._on_backend_change("gemini")
        key = _resolve_api_key(app)
        if key:
            _run_expand_internal(app, xml, key, "gemini", retry=True)
        else:
            _show_api_key_dialog(
                app,
                title="Enter API key",
                message="Paste your Gemini API key to use online Gemini:",
                on_ok=lambda k, s: run_with_key(k, s),
            )

    def cancel() -> None:
        app.expand_btn.config(state=tk.NORMAL)
        _close_error_dialog(win, app, focus_main=True)

    btns = tk.Frame(f)
    btns.pack(fill=tk.X, pady=(12, 0))
    tk.Button(btns, text="Enter API key", command=enter_key).pack(side=tk.LEFT, padx=(0, 4))
    tk.Button(btns, text="Use local model", command=use_local).pack(side=tk.LEFT, padx=(0, 4))
    tk.Button(btns, text="Use online Gemini", command=use_online).pack(side=tk.LEFT, padx=(0, 4))
    tk.Button(btns, text="Cancel", command=cancel).pack(side=tk.LEFT)
    win.geometry("+%d+%d" % (app.root.winfo_rootx() + 50, app.root.winfo_rooty() + 60))


def _run_expand_internal(
    app: "App",
    xml: str,
    api_key: str | None,
    backend: str,
    *,
    retry: bool = False,
) -> None:
    # Always reload examples from disk (retrain) so Train additions are used on retry.
    # "Layered Training": include learned_examples.json in the prompt when checked (any backend).
    examples_path = Path(app.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
    include_learned = bool(getattr(app, "include_learned_var", None) and app.include_learned_var.get())
    try:
        examples = load_examples(examples_path, include_learned=bool(include_learned))
    except ValueError as e:
        messagebox.showerror("Examples", str(e))
        return
    if not retry:
        if not xml.strip():
            messagebox.showwarning("Expand", "Input is empty. Open an XML file or paste XML.")
            return
        if not examples and not messagebox.askyesno("No examples", "No examples loaded. Add pairs in Train or use examples.json. Continue anyway?"):
            return
        app.original_input = xml
    # Use selected model from dropdown for Gemini, or default local model
    if backend == "gemini":
        model = app.gemini_model_var.get().strip() or app.model_gemini
        if model not in GEMINI_MODELS:
            model = app.model_gemini
    else:
        model = app.model_local
    modality = app.modality_var.get().strip() or "full"
    if modality not in MODALITIES:
        modality = "full"
    try:
        mc = int(app.concurrent_var.get().strip() or "2")
        max_concurrent = max(1, min(8, mc))
    except (ValueError, AttributeError):
        max_concurrent = 2
    try:
        pv = int(app.passes_var.get().strip() or "1")
        passes = max(1, min(5, pv))
    except (ValueError, AttributeError):
        passes = 1
    _status(app, "Expanding…")
    # Update Expand button text to show queue status
    app._update_expand_button_text()
    app.last_expand_xml = xml
    app.last_expand_api_key = api_key
    app.last_expand_backend = backend
    app.last_expand_model = model
    # Progress/hang tracking and run ID (prevents stale on_done from overwriting)
    app.expand_start_time = time.time()
    app.last_progress_time = time.time()
    app.expand_running = True
    app.cancel_requested = False
    app.expand_run_id = getattr(app, "expand_run_id", 0) + 1
    whole_doc = app.whole_document_var.get() if getattr(app, "whole_document_var", None) else False
    app._expand_whole_doc = whole_doc  # Hang check uses longer threshold for whole-doc
    if whole_doc:
        app.progress_bar.configure(mode="indeterminate")
        app.progress_bar.start(10)
    else:
        app.progress_bar.configure(mode="determinate")
        app.progress_bar["value"] = 0
    app.cancel_btn.config(state=tk.NORMAL)
    # Start processing animation
    app._processing_frame = 0
    app._base_status = "Starting…"
    _update_processing_indicator(app)
    _start_hang_check(app)
    run_id = app.expand_run_id
    app._expand_examples_path = examples_path if not include_learned else None
    app._expand_include_learned = include_learned
    t = threading.Thread(
        target=_expand_worker,
        args=(xml, examples, api_key, app, backend, model, modality, max_concurrent, passes, run_id),
        daemon=True,
    )
    t.start()


_APP_NAME = "Expand diplomatic"


def _set_app_display_name() -> None:
    """Set process/window name for Dock, taskbar, hover, right-click. Optional: setproctitle."""
    try:
        import setproctitle
        setproctitle.setproctitle(_APP_NAME)
    except (ImportError, OSError, AttributeError):
        pass  # setproctitle unavailable or unsupported (e.g. Windows)


class App:
    def __init__(self) -> None:
        _set_app_display_name()
        self.root = tk.Tk()
        from expand_diplomatic._version import __version__
        self.root.title(f"{_APP_NAME} v{__version__}")
        try:
            self.root.wm_iconname(_APP_NAME)  # Icon/taskbar name on hover
        except Exception:
            pass
        self.root.minsize(600, 400)
        self.root.geometry("900x550")
        _icon_path = ROOT_DIR / "stretch_armstrong_icon.png"
        if _icon_path.exists():
            try:
                self._icon_img = tk.PhotoImage(file=str(_icon_path))
                self.root.iconphoto(True, self._icon_img)
            except Exception:
                self._icon_img = None
        else:
            self._icon_img = None

        self.status_var = tk.StringVar(value="Idle")
        self.examples_var = tk.StringVar(value=str(DEFAULT_EXAMPLES))
        self.expand_btn: tk.Button = None  # set later
        # Courier common on Unix; Courier New on Windows
        self._font = ("Courier New", 10) if os.name == "nt" else ("Courier", 10)
        self._font_sm = ("Courier New", 9) if os.name == "nt" else ("Courier", 9)
        self.session_api_key: str | None = None
        self.backend: str = "gemini"
        self.model_gemini: str = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self.model_local: str = "llama3.2"
        self.last_expand_xml = ""
        self.original_input = ""  # Source for Re-expand (set on Open/Expand)
        self.last_expand_api_key: str | None = None
        self.last_expand_backend = "gemini"
        self.last_expand_model = DEFAULT_GEMINI_MODEL
        self.last_dir: Path | None = None  # last Open/Save directory, for file dialogs
        self.last_input_path: Path | None = None  # last opened XML file (for TXT default names)
        self.last_output_path: Path | None = None  # file currently shown in output panel (for companion sync)
        self.folder_files: list[Path] = []  # XML files in current folder for Prev/Next
        self.folder_index: int = -1
        self.backend_var = tk.StringVar(value="gemini")
        self.modality_var = tk.StringVar(value="full")
        self.gemini_model_var = tk.StringVar(value=self.model_gemini)
        self.time_label_var = tk.StringVar(value="")
        self.format_label_var = tk.StringVar(value="")  # PAGE or TEI format indicator
        # Progress/hang tracking
        self.progress_bar: ttk.Progressbar = None  # set in _build_status
        self.expand_start_time: float = 0.0
        self.last_progress_time: float = 0.0
        self.expand_running: bool = False
        self.hang_check_id: str | None = None
        self._high_end_gpu = False
        try:
            from expand_diplomatic.gpu_detect import detect_high_end_gpu
            self._high_end_gpu = detect_high_end_gpu()
        except Exception:
            pass
        self.auto_learn_var = tk.BooleanVar(value=True)
        self.include_learned_var = tk.BooleanVar(value=self._high_end_gpu)
        self.whole_document_var = tk.BooleanVar(value=False)  # Default: block-by-block
        self._restart_with_block_by_block = False  # Set when user switches to block-by-block during run
        self.autosave_var = tk.BooleanVar(value=True)
        self.autosave_after_id: str | None = None
        self.autosave_idle_ms = 3000
        self._processing_frame = 0
        self._base_status = ""
        self.image_path: Path | None = None
        self._image_photo: tk.PhotoImage | None = None
        self._image_panel_expanded = False
        # Batch processing state
        self._batch_files: list[Path] = []
        self._batch_status: dict[str, str] = {}  # filename -> "pending"/"processing"/"done"/"failed"
        self._batch_panel_expanded = False
        # Expansion queue
        self._expand_queue: list[dict] = []  # List of {"xml": str, "api_key": str|None, "backend": str, "path": Path|None}
        self._queue_label_var = tk.StringVar(value="")
        # Block sync: preserve selection when output updates during expansion
        self._synced_block_idx: int | None = None

        self._build_toolbar()
        self._build_main()
        self._build_batch_panel()
        self._build_train()
        self._build_status()
        self._apply_preferences(_load_preferences())
        self.root.protocol("WM_DELETE_WINDOW", self._on_quit)
        # Defer Gemini model fetch to background (ideasrule-style fast startup)
        self.root.after(200, self._refresh_models_background)

    def _build_toolbar(self) -> None:
        # Top third: toolbar fills width and moves with window resizing; essential row always visible
        toolbar_wrapper = tk.Frame(self.root, relief=tk.FLAT, bd=0)
        toolbar_wrapper.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)
        pad = dict(padx=2, pady=2)
        opts = {"font": ("", 9), "takefocus": True}
        # Essential row (fixed): Open, Batch, Expand, Re-expand, Save, prev/next — always visible
        essential_row = tk.Frame(toolbar_wrapper, relief=tk.FLAT, bd=0)
        essential_row.pack(side=tk.TOP, fill=tk.X)
        for w in [
            (tk.Button, "Open", self._on_open, {"width": 4}),
            (tk.Button, "Batch…", self._on_batch, {"width": 6}),
            (tk.Button, "Expand", self._on_expand, {"width": 5}),
            (tk.Button, "Re-expand", self._on_reexpand, {"width": 8}),
            (tk.Button, "Save", self._on_save, {"width": 4}),
            (tk.Button, "◀", self._on_prev_file, {"width": 2}),
            (tk.Button, "▶", self._on_next_file, {"width": 2}),
        ]:
            cls, txt, cmd, kw = w
            btn = cls(essential_row, text=txt, command=cmd, **{**pad, **kw})
            btn.pack(side=tk.LEFT, **pad)
            if txt == "Expand":
                self.expand_btn = btn
        # Scrollable area: secondary actions + settings (moves with window, scrolls when narrow)
        self._toolbar_canvas = tk.Canvas(toolbar_wrapper, highlightthickness=0, height=56)
        self._toolbar_scrollbar = tk.Scrollbar(toolbar_wrapper, orient=tk.HORIZONTAL, command=self._toolbar_canvas.xview)
        self._toolbar_canvas.configure(xscrollcommand=self._toolbar_scrollbar.set)
        self._toolbar_canvas.pack(side=tk.TOP, fill=tk.X)
        self._toolbar_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        bar = tk.Frame(self._toolbar_canvas, relief=tk.FLAT, bd=0)
        self._toolbar_frame = bar
        self._toolbar_canvas_window = self._toolbar_canvas.create_window(0, 0, window=bar, anchor=tk.NW)
        self._toolbar_canvas.bind("<Configure>", self._on_toolbar_canvas_configure)
        bar.bind("<Configure>", lambda e: self._schedule_toolbar_scroll())
        self._toolbar_scroll_after_id: str | None = None
        self.root.after(50, self._update_toolbar_scroll)
        # Row 0: Secondary actions (export, Diff)
        r1 = tk.Frame(bar)
        r1.pack(side=tk.TOP, fill=tk.X)
        for w in [
            (tk.Button, "In→TXT", self._on_save_input_txt, {"width": 5}),
            (tk.Button, "Out→TXT", self._on_save_output_txt, {"width": 6}),
            (tk.Button, "Diff", self._on_diff, {"width": 4}),
        ]:
            cls, txt, cmd, kw = w
            cls(r1, text=txt, command=cmd, **{**pad, **kw}).pack(side=tk.LEFT, **pad)
        # Row 1: Settings (grid so Examples entry expands)
        r2 = tk.Frame(bar)
        r2.pack(side=tk.TOP, fill=tk.X)
        r2.columnconfigure(17, weight=1, minsize=80)  # Examples entry expands
        col = 0
        tk.Label(r2, text="Backend", **opts).grid(row=0, column=col, **pad)
        col += 1
        tk.OptionMenu(r2, self.backend_var, *BACKENDS, command=self._on_backend_change).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        self._model_label = tk.Label(r2, text="Model", **opts)
        self._model_label.grid(row=0, column=col, **pad)
        col += 1
        self._model_menu = tk.OptionMenu(r2, self.gemini_model_var, *GEMINI_MODELS)
        self._model_menu.grid(row=0, column=col, sticky=tk.W, **pad)
        # Rebuild with speed tick marks (more · = faster)
        _apply_model_menu_labels(self._model_menu, self.gemini_model_var, GEMINI_MODELS)
        _add_tooltip(self._model_menu, "Gemini model. More · = faster. Default = best value.")
        col += 1
        self._model_refresh_btn = tk.Button(r2, text="⟳", width=2, command=self._on_refresh_models, **opts)
        self._model_refresh_btn.grid(row=0, column=col, **pad)
        col += 1
        tk.Label(r2, text="Mod", **opts).grid(row=0, column=col, **pad)
        col += 1
        tk.OptionMenu(r2, self.modality_var, *MODALITIES).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Label(r2, text="Simul.", **opts).grid(row=0, column=col, **pad)
        col += 1
        _conc_max = 16 if self._high_end_gpu else 8
        self.concurrent_var = tk.StringVar(value="2")
        self._concurrent_spinbox = tk.Spinbox(r2, from_=1, to=_conc_max, width=2, textvariable=self.concurrent_var)
        self._concurrent_spinbox.grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Label(r2, text="Pass", **opts).grid(row=0, column=col, **pad)
        col += 1
        self.passes_var = tk.StringVar(value="1")
        tk.Spinbox(r2, from_=1, to=5, width=2, textvariable=self.passes_var).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Label(r2, text="Expand", **opts).grid(row=0, column=col, **pad)
        col += 1
        expand_toggle = tk.Frame(r2)
        expand_toggle.grid(row=0, column=col, sticky=tk.W, **pad)
        rb_whole = tk.Radiobutton(expand_toggle, text="Whole doc", variable=self.whole_document_var, value=True, **opts)
        rb_whole.pack(side=tk.LEFT)
        rb_block = tk.Radiobutton(expand_toggle, text="Block-by-block", variable=self.whole_document_var, value=False, **opts)
        rb_block.pack(side=tk.LEFT)
        _add_tooltip(rb_whole, "Expand entire document in one API call")
        _add_tooltip(rb_block, "Expand each block separately; shows per-block progress (default). Switch during run to cancel and restart.")
        self.whole_document_var.trace_add("write", self._on_whole_doc_change)
        col += 1
        tk.Checkbutton(r2, text="Learn", variable=self.auto_learn_var, **opts).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Checkbutton(r2, text="Layered Training", variable=self.include_learned_var, **opts).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Checkbutton(r2, text="Autosave", variable=self.autosave_var, **opts).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Label(r2, text="Examples", **opts).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        self._examples_entry = tk.Entry(r2, textvariable=self.examples_var)
        self._examples_entry.grid(row=0, column=col, sticky=tk.EW, **pad)
        col += 1
        tk.Button(r2, text="…", width=2, command=self._on_browse_examples).grid(row=0, column=col, **pad)
        col += 1
        tk.Button(r2, text="Refresh", width=6, command=self._refresh_train_list).grid(row=0, column=col, **pad)
        col += 1
        tk.Button(r2, text="Test", width=4, command=self._on_test_connection).grid(row=0, column=col, **pad)
        # Keyboard shortcuts (Ctrl+O/S/E, Left/Right for prev/next file)
        self.root.bind("<Control-o>", lambda e: (self._on_open(), "break")[1])
        self.root.bind("<Control-s>", lambda e: (self._on_save(), "break")[1])
        self.root.bind("<Control-e>", lambda e: (self._on_expand(), "break")[1])
        self.root.bind("<Control-Left>", lambda e: (self._on_prev_file(), "break")[1])
        self.root.bind("<Control-Right>", lambda e: (self._on_next_file(), "break")[1])
        self._on_backend_change(self.backend_var.get())

    def _on_toolbar_canvas_configure(self, event: tk.Event) -> None:
        """Schedule toolbar scroll update (throttled) so resize doesn't hammer layout."""
        self._schedule_toolbar_scroll()

    def _schedule_toolbar_scroll(self) -> None:
        """Throttle: run _update_toolbar_scroll once after 50 ms of no resize."""
        if self._toolbar_scroll_after_id is not None:
            self.root.after_cancel(self._toolbar_scroll_after_id)
        self._toolbar_scroll_after_id = self.root.after(50, self._do_toolbar_scroll)

    def _do_toolbar_scroll(self) -> None:
        self._toolbar_scroll_after_id = None
        self._update_toolbar_scroll()

    def _update_toolbar_scroll(self) -> None:
        """Update toolbar scroll region and canvas window size so top third moves with window resizing.
        When narrow: horizontal scroll; when wide: canvas window fills viewport so toolbar uses full width."""
        self._toolbar_frame.update_idletasks()
        req_w = self._toolbar_frame.winfo_reqwidth()
        h = self._toolbar_frame.winfo_reqheight()
        canvas_w = max(1, self._toolbar_canvas.winfo_width() or 400)
        w = max(req_w, canvas_w)
        self._toolbar_canvas.configure(scrollregion=(0, 0, w, h))
        self._toolbar_canvas.itemconfig(self._toolbar_canvas_window, width=w, height=h)
        self._toolbar_canvas.configure(height=min(h, 120))

    def _on_backend_change(self, backend: str) -> None:
        """Show or hide Gemini model dropdown; when local+GPU, suggest higher Parallel."""
        is_local = backend.strip().lower() == "local"
        if is_local:
            self._model_label.grid_remove()
            self._model_menu.grid_remove()
            if self._high_end_gpu:
                self.concurrent_var.set("12")
                self._concurrent_spinbox.configure(to=16)
        else:
            self._model_label.grid()
            self._model_menu.grid()
            self._concurrent_spinbox.configure(to=8)
            try:
                v = int(self.concurrent_var.get().strip() or "2")
                if v > 8:
                    self.concurrent_var.set("8")
            except ValueError:
                self.concurrent_var.set("2")
        self.root.after(10, self._update_toolbar_scroll)

    def _build_main(self) -> None:
        panes = tk.Frame(self.root)
        panes.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=2)

        # Image strip at top (collapsible): arrow only, flat strip
        self._image_top = tk.Frame(panes)
        self._image_top.pack(side=tk.TOP, fill=tk.X, padx=2, pady=0)
        self._image_collapsed_strip = tk.Frame(self._image_top, height=24, relief=tk.FLAT, bd=0)
        self._image_collapsed_strip.pack(side=tk.TOP, fill=tk.X)
        self._image_collapsed_strip.pack_propagate(False)
        tk.Button(
            self._image_collapsed_strip, text="▶", font=("", 9), width=2,
            command=self._toggle_image_panel,
        ).pack(side=tk.LEFT, padx=2, pady=1)
        self._image_panel = tk.Frame(self._image_top, height=220, relief=tk.FLAT, bd=0)
        self._image_panel.pack_propagate(False)
        img_header = tk.Frame(self._image_panel)
        img_header.pack(fill=tk.X, padx=2, pady=2)
        tk.Button(img_header, text="▼", width=2, font=("", 9), command=self._toggle_image_panel).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(img_header, text="Add", width=4, font=("", 9), command=self._on_upload_image).pack(side=tk.LEFT)
        self._image_canvas = tk.Canvas(self._image_panel, bg="gray95", highlightthickness=0)
        self._image_canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self._image_canvas.bind("<Configure>", self._on_image_canvas_configure)

        # Input and output panels
        content_row = tk.Frame(panes)
        content_row.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=0, pady=2)
        left = tk.LabelFrame(content_row, text="Input", font=("", 9))
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        opts = {"wrap": tk.WORD, "font": self._font, "exportselection": False}
        self.input_txt = scrolledtext.ScrolledText(left, **opts)
        self.input_txt.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        right = tk.LabelFrame(content_row, text="Output", font=("", 9))
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.output_txt = scrolledtext.ScrolledText(right, **opts)
        self.output_txt.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        # Paired highlight: visible when widget is unfocused (Windows hides "sel" when unfocused)
        for w in (self.input_txt, self.output_txt):
            w.tag_configure("paired", background="#b3d9ff")
        self.input_txt.bind("<Button-1>", self._on_panel_click)
        self.output_txt.bind("<Button-1>", self._on_panel_click)
        self.input_txt.bind("<Double-Button-1>", self._on_panel_double_click)
        self.output_txt.bind("<Double-Button-1>", self._on_panel_double_click)
        self.input_txt.bind("<KeyRelease>", self._on_input_activity)
        self.output_txt.bind("<KeyRelease>", self._on_input_activity)

    def _build_batch_panel(self) -> None:
        """Build collapsible batch file list panel (hidden by default)."""
        self._batch_frame = tk.LabelFrame(self.root, text="Batch", font=("", 9))
        header = tk.Frame(self._batch_frame, relief=tk.FLAT)
        header.pack(fill=tk.X, padx=2, pady=2)
        self._batch_toggle_btn = tk.Button(
            header, text="▶", width=2, command=self._toggle_batch_list, font=("", 9),
        )
        self._batch_toggle_btn.pack(side=tk.LEFT, padx=2)
        self._batch_summary_var = tk.StringVar(value="")
        tk.Label(header, textvariable=self._batch_summary_var, font=("", 9), anchor=tk.W).pack(side=tk.LEFT, padx=4)
        tk.Button(header, text="✕", width=2, command=self._hide_batch_panel, font=("", 9)).pack(side=tk.RIGHT, padx=2)
        self._batch_list_frame = tk.Frame(self._batch_frame, relief=tk.FLAT)
        self._batch_listbox = scrolledtext.ScrolledText(
            self._batch_list_frame, height=6, wrap=tk.NONE, state=tk.DISABLED,
            font=("Courier", 9), bg="#fafafa", relief=tk.FLAT,
        )
        self._batch_listbox.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        # Tags for status colors
        self._batch_listbox.tag_configure("pending", foreground="#888")
        self._batch_listbox.tag_configure("processing", foreground="#0066cc", background="#e6f0ff")
        self._batch_listbox.tag_configure("done", foreground="#228B22")
        self._batch_listbox.tag_configure("failed", foreground="#cc0000", background="#ffe6e6")
        # Start collapsed
        self._batch_list_expanded = False

    def _toggle_batch_list(self) -> None:
        """Toggle visibility of the batch file list."""
        if self._batch_list_expanded:
            self._batch_list_frame.pack_forget()
            self._batch_toggle_btn.config(text="▶")
            self._batch_list_expanded = False
        else:
            self._batch_list_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
            self._batch_toggle_btn.config(text="▼")
            self._batch_list_expanded = True

    def _show_batch_panel(self, files: list) -> None:
        """Show and populate the batch panel with files."""
        self._batch_files = files
        self._batch_status = {f.name: "pending" for f in files}
        self._update_batch_list()
        self._batch_frame.pack(side=tk.TOP, fill=tk.X, padx=4, pady=2, before=self._train_frame)
        # Auto-expand if there are files
        if not self._batch_list_expanded:
            self._toggle_batch_list()

    def _hide_batch_panel(self) -> None:
        """Hide the batch panel."""
        self._batch_frame.pack_forget()
        self._batch_files = []
        self._batch_status = {}

    def _update_batch_list(self) -> None:
        """Refresh the batch file list with current status."""
        self._batch_listbox.config(state=tk.NORMAL)
        self._batch_listbox.delete("1.0", tk.END)
        done = sum(1 for s in self._batch_status.values() if s == "done")
        failed = sum(1 for s in self._batch_status.values() if s == "failed")
        total = len(self._batch_files)
        self._batch_summary_var.set(f"({done}/{total} done" + (f", {failed} failed)" if failed else ")"))
        for f in self._batch_files:
            status = self._batch_status.get(f.name, "pending")
            icon = {"pending": "○", "processing": "◉", "done": "✓", "failed": "✗"}.get(status, "○")
            line = f"{icon} {f.name}\n"
            self._batch_listbox.insert(tk.END, line, status)
        self._batch_listbox.config(state=tk.DISABLED)

    def _update_batch_file_status(self, filename: str, status: str) -> None:
        """Update status for a single file and refresh the list."""
        self._batch_status[filename] = status
        self.root.after(0, self._update_batch_list)

    def _toggle_image_panel(self) -> None:
        """Expand or collapse the image panel."""
        if self._image_panel_expanded:
            self._image_panel.pack_forget()
            self._image_collapsed_strip.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)
            self._image_panel_expanded = False
        else:
            self._image_collapsed_strip.pack_forget()
            self._image_panel.pack(side=tk.TOP, fill=tk.X, padx=0, pady=2)
            self._image_panel_expanded = True
            if self.image_path is not None:
                self.root.after(50, lambda: self._display_image(self.image_path))

    def _on_upload_image(self) -> None:
        """Open file dialog and load an image."""
        d = self._file_dialog_dir()
        path = filedialog.askopenfilename(
            title="Select image",
            initialdir=str(d),
            filetypes=[
                ("All images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tiff *.tif *.ico"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        p = Path(path)
        try:
            self.image_path = p
            self._display_image(p)
            _status(self, f"Image: {p.name}")
        except Exception as e:
            messagebox.showerror("Image", f"Could not load image: {e}")

    def _on_image_canvas_configure(self, event: tk.Event) -> None:
        """Rescale image when canvas is resized."""
        if self.image_path is not None and event.width > 10 and event.height > 10:
            self._display_image(self.image_path)

    def _display_image(self, path: Path) -> None:
        """Display image in the canvas, scaled to fit."""
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            cw = max(40, self._image_canvas.winfo_width() or 260)
            ch = max(40, self._image_canvas.winfo_height() or 200)
            img.thumbnail((cw, ch), Image.LANCZOS)
            self._image_photo = ImageTk.PhotoImage(img)
            self._image_canvas.delete("all")
            cx, cy = cw // 2, ch // 2
            self._image_canvas.create_image(cx, cy, image=self._image_photo, anchor=tk.CENTER)
        except Exception:
            pass

    def _on_input_activity(self, event: tk.Event) -> None:
        """Schedule autosave when input goes idle."""
        if self.autosave_after_id is not None:
            try:
                self.root.after_cancel(self.autosave_after_id)
            except Exception:
                pass
            self.autosave_after_id = None
        if not getattr(self, "autosave_var", None) or not self.autosave_var.get():
            return

        def do_autosave() -> None:
            self.autosave_after_id = None
            self._do_autosave()

        self.autosave_after_id = self.root.after(self.autosave_idle_ms, do_autosave)

    def _do_autosave(self) -> None:
        """Save input and output to files when idle. Creates new files if none previously saved."""
        if not getattr(self, "autosave_var", None) or not self.autosave_var.get():
            return
        if self.expand_running:
            return
        base = self._file_dialog_dir()
        saved: list[str] = []
        # Input
        xml = self.input_txt.get("1.0", tk.END)
        if xml.strip():
            path = getattr(self, "last_input_path", None)
            if path is None:
                path = base / "autosave.xml"
                self.last_input_path = path
                self.last_dir = base
            try:
                path.write_text(xml, encoding="utf-8")
                saved.append(path.name)
            except Exception:
                pass
        # Output: create new file if no output path previously saved
        out_xml = self.output_txt.get("1.0", tk.END)
        if out_xml.strip():
            out_path = getattr(self, "last_output_path", None)
            if out_path is None:
                if getattr(self, "last_input_path", None) is not None:
                    out_path = self.last_input_path.parent / f"{self.last_input_path.stem}_expanded.xml"
                else:
                    out_path = base / "autosave_expanded.xml"
                self.last_output_path = out_path
                self.last_dir = base
            try:
                out_path.write_text(out_xml, encoding="utf-8")
                saved.append(out_path.name)
            except Exception:
                pass
        if saved:
            _status(self, f"Autosaved {', '.join(saved)}")

    def _build_train(self) -> None:
        tr = tk.LabelFrame(self.root, text="Train", font=("", 9))
        tr.pack(side=tk.TOP, fill=tk.X, padx=4, pady=2)
        self._train_frame = tr
        row = tk.Frame(tr)
        row.pack(fill=tk.X, padx=2, pady=2)
        row.columnconfigure(1, weight=1)
        row.columnconfigure(4, weight=1)
        pad = dict(padx=2, pady=2)
        tk.Label(row, text="Diplomatic", font=("", 9)).grid(row=0, column=0, sticky=tk.W, **pad)
        self.dip_var = tk.StringVar()
        dip_entry = tk.Entry(row, textvariable=self.dip_var)
        dip_entry.grid(row=0, column=1, sticky=tk.EW, **pad)
        tk.Button(row, text="In", width=3, font=("", 9), command=self._on_dip_from_input).grid(row=0, column=2, **pad)
        tk.Label(row, text="Full", font=("", 9)).grid(row=0, column=3, sticky=tk.W, **pad)
        self.full_var = tk.StringVar()
        full_entry = tk.Entry(row, textvariable=self.full_var)
        full_entry.grid(row=0, column=4, sticky=tk.EW, **pad)
        tk.Button(row, text="Out", width=3, font=("", 9), command=self._on_full_from_output).grid(row=0, column=5, **pad)
        add_btn = tk.Button(row, text="Add", width=4, font=("", 9), command=self._on_add_example)
        add_btn.grid(row=0, column=6, **pad)
        def _add_on_ctrl_return(_e) -> str:
            self._on_add_example()
            return "break"

        for w in (dip_entry, full_entry):
            w.bind("<Control-Return>", _add_on_ctrl_return)
        search_row = tk.Frame(tr)
        search_row.pack(fill=tk.X, padx=2, pady=(0, 2))
        tk.Label(search_row, text="Search", font=("", 9)).pack(side=tk.LEFT, padx=(0, 4), pady=2)
        self._train_search_var = tk.StringVar()
        self._train_refresh_after_id: str | None = None
        self._train_search_var.trace_add("write", self._schedule_train_refresh)
        search_entry = tk.Entry(search_row, textvariable=self._train_search_var, width=14, font=("", 9))
        search_entry.pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(search_row, text="✕", width=2, font=("", 9), command=lambda: self._train_search_var.set("")).pack(side=tk.LEFT, padx=2, pady=2)
        self.train_list = scrolledtext.ScrolledText(tr, height=3, wrap=tk.WORD, state=tk.DISABLED, font=self._font_sm)
        self.train_list.pack(fill=tk.X, padx=2, pady=2)
        self._refresh_train_list()

    def _build_status(self) -> None:
        status_frame = tk.Frame(self.root, relief=tk.FLAT, bd=0)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=2)
        status_frame.columnconfigure(1, weight=1)
        # Status message
        tk.Label(status_frame, textvariable=self.status_var, anchor=tk.W, font=("", 9)).grid(
            row=0, column=0, sticky=tk.W, padx=(4, 8), pady=2
        )
        # Progress bar (expandable)
        self.progress_bar = ttk.Progressbar(
            status_frame, orient=tk.HORIZONTAL, mode="determinate"
        )
        self.progress_bar.grid(row=0, column=1, sticky=tk.EW, padx=4, pady=2)
        # Elapsed time
        tk.Label(status_frame, textvariable=self.time_label_var, width=5, anchor=tk.E, font=("", 9)).grid(
            row=0, column=2, sticky=tk.E, padx=2, pady=2
        )
        # Format indicator (PAGE/TEI) - plain text label
        self._format_label = tk.Label(
            status_frame, textvariable=self.format_label_var, width=4, anchor=tk.CENTER,
            font=("", 9), fg="white"
        )
        self._format_label.grid(row=0, column=3, sticky=tk.W, padx=(4, 2), pady=2)
        # Queue label
        self._queue_label = tk.Label(
            status_frame, textvariable=self._queue_label_var, width=10, anchor=tk.CENTER,
            font=("", 9), fg="#88ff88"
        )
        self._queue_label.grid(row=0, column=4, sticky=tk.W, padx=(2, 2), pady=2)
        # Clear queue button (only visible when queue has items)
        self._clear_queue_btn = tk.Button(
            status_frame, text="Clear Q", command=self._clear_queue, width=6, font=("", 9)
        )
        self._clear_queue_btn.grid(row=0, column=5, padx=(2, 2), pady=2)
        self._clear_queue_btn.grid_remove()  # Hidden by default
        # Cancel button
        self.cancel_btn = tk.Button(
            status_frame, text="Cancel", command=self._on_cancel_expand, state=tk.DISABLED, font=("", 9)
        )
        self.cancel_btn.grid(row=0, column=6, padx=(2, 4), pady=2)

    def _get_block_ranges_cached(self, content: str) -> list[tuple[int, int]]:
        """Block ranges for content, cached to avoid re-parsing on repeated clicks."""
        cache = getattr(self, "_block_ranges_cache", None)
        if cache is None:
            self._block_ranges_cache = {}
            cache = self._block_ranges_cache
        if content in cache:
            return cache[content]
        from expand_diplomatic.expander import get_block_ranges
        ranges = get_block_ranges(content)
        if len(cache) >= 4:  # Keep input+output for both panels
            cache.clear()
        cache[content] = ranges
        return ranges

    def _get_block_at_click(self, widget: tk.Text, event: tk.Event) -> tuple[int | None, list[tuple[int, int]], str]:
        """Return (block_idx, ranges, content) for the block at click position, or (None, [], content)."""
        try:
            idx = widget.index(f"@{event.x},{event.y}")
        except Exception:
            return (None, [], "")
        if not idx:
            return (None, [], "")
        content = widget.get("1.0", tk.END)
        try:
            char_offset = widget.count("1.0", idx, "chars")[0]
        except Exception:
            return (None, [], content)
        ranges = self._get_block_ranges_cached(content)
        for i, (start, end) in enumerate(ranges):
            if start <= char_offset < end:
                return (i, ranges, content)
        return (None, ranges, content)

    def _on_panel_click(self, event: tk.Event) -> None:
        """On click in input or output, select the parallel block in the other panel and align vertically."""
        widget = event.widget
        block_idx, _, _ = self._get_block_at_click(widget, event)
        if block_idx is None:
            return
        other = self.output_txt if widget is self.input_txt else self.input_txt
        other_content = other.get("1.0", tk.END)
        other_ranges = self._get_block_ranges_cached(other_content)
        if block_idx >= len(other_ranges):
            return
        start, end = other_ranges[block_idx]
        start_idx = other.index(f"1.0 + {start} chars")
        end_idx = other.index(f"1.0 + {end} chars")
        other.tag_remove("paired", "1.0", tk.END)
        other.tag_add("paired", start_idx, end_idx)
        other.mark_set("insert", start_idx)
        self._synced_block_idx = block_idx
        # Scroll to align both blocks at same vertical position
        try:
            clicked_line = widget.index(f"@{event.x},{event.y}").split('.')[0]
            widget.see(f"{clicked_line}.0")
            other_line = start_idx.split('.')[0]
            other.see(f"{other_line}.0")
        except Exception:
            other.see(start_idx)

    def _on_panel_double_click(self, event: tk.Event) -> None:
        """On double-click, snap selection to the entire block at clicked position in both panels.
        If input/output files are mismatched, load the correct paired file."""
        widget = event.widget
        block_idx, ranges, content = self._get_block_at_click(widget, event)
        if block_idx is None:
            return
        
        # Check if files are mismatched and load paired file if needed
        is_input_panel = (widget is self.input_txt)
        self._check_and_load_paired_file(is_input_panel)
        start, end = ranges[block_idx]
        
        # Select full block in clicked widget
        start_idx = widget.index(f"1.0 + {start} chars")
        end_idx = widget.index(f"1.0 + {end} chars")
        widget.tag_remove("sel", "1.0", tk.END)
        widget.tag_add("sel", start_idx, end_idx)
        widget.mark_set("insert", start_idx)
        # Sync selection to corresponding block in other panel and align vertically
        other = self.output_txt if widget is self.input_txt else self.input_txt
        other_content = other.get("1.0", tk.END)
        other_ranges = self._get_block_ranges_cached(other_content)
        if block_idx < len(other_ranges):
            o_start, o_end = other_ranges[block_idx]
            o_start_idx = other.index(f"1.0 + {o_start} chars")
            o_end_idx = other.index(f"1.0 + {o_end} chars")
            other.tag_remove("paired", "1.0", tk.END)
            other.tag_add("paired", o_start_idx, o_end_idx)
            other.mark_set("insert", o_start_idx)
            self._synced_block_idx = block_idx
            # Scroll both panels to align the blocks at same vertical position
            try:
                clicked_line = start_idx.split('.')[0]
                widget.see(f"{clicked_line}.0")
                other_line = o_start_idx.split('.')[0]
                other.see(f"{other_line}.0")
            except Exception:
                widget.see(start_idx)
                other.see(o_start_idx)
        return "break"  # Prevent default word selection
    
    def _check_and_load_paired_file(self, clicked_input_panel: bool) -> bool:
        """On double-click, load the companion XML into the other panel so the matching line is shown in the correct file.
        Returns True if a file was loaded, False otherwise."""
        if clicked_input_panel:
            # Double-clicked in input: open companion output file (input_stem_expanded.xml) in output panel
            if self.last_input_path is None:
                return False
            expected_output = self.last_input_path.parent / f"{self.last_input_path.stem}_expanded.xml"
            if not expected_output.exists():
                return False
            # Load companion into output unless it's already showing that file
            if self.last_output_path is None or self.last_output_path.resolve() != expected_output.resolve():
                try:
                    output_text = expected_output.read_text(encoding="utf-8")
                    self.output_txt.delete("1.0", tk.END)
                    self.output_txt.insert("1.0", output_text)
                    self.output_txt.see("1.0")
                    self.last_output_path = expected_output
                    _status(self, f"Loaded companion: {expected_output.name}")
                    return True
                except Exception:
                    return False
            return False
        else:
            # Double-clicked in output: open companion input file (base .xml) in input panel
            if self.last_output_path is None:
                return False
            stem = self.last_output_path.stem
            if "_expanded" not in stem:
                return False
            base_name = stem.replace("_expanded", "")
            expected_input = self.last_output_path.parent / f"{base_name}.xml"
            if not expected_input.exists():
                return False
            # Load companion into input unless it's already showing that file
            if self.last_input_path is None or self.last_input_path.resolve() != expected_input.resolve():
                try:
                    input_text = expected_input.read_text(encoding="utf-8")
                    self.input_txt.delete("1.0", tk.END)
                    self.input_txt.insert("1.0", input_text)
                    self.input_txt.see("1.0")
                    self.last_input_path = expected_input
                    self.original_input = input_text
                    _status(self, f"Loaded companion: {expected_input.name}")
                    return True
                except Exception:
                    return False
            return False

    def _file_dialog_dir(self) -> Path:
        """Directory for file dialogs: last path from any file selection, else examples dir, else project root."""
        d = self.last_dir
        if d is not None and d.is_dir():
            return d
        if self.last_input_path is not None:
            p = self.last_input_path.parent
            if p.is_dir():
                return p
        ex = Path(self.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
        if ex.parent.is_dir():
            return ex.parent
        return ROOT_DIR

    def _on_open(self) -> None:
        path = filedialog.askopenfilename(
            title="Open XML",
            initialdir=str(self._file_dialog_dir()),
            filetypes=[("XML", "*.xml"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            p = Path(path)
            text = p.read_text(encoding="utf-8")
            self.input_txt.delete("1.0", tk.END)
            self.input_txt.insert("1.0", text)
            self.original_input = text
            self.last_dir = p.parent
            self.last_input_path = p
            self.folder_files = sorted(p.parent.glob("*.xml"))
            self.folder_index = next((i for i, f in enumerate(self.folder_files) if f.resolve() == p.resolve()), -1)
            _block_ranges_cache = getattr(self, "_block_ranges_cache", None)
            if _block_ranges_cache is not None:
                _block_ranges_cache.clear()
            self._load_expanded_if_exists(p)
            # Detect format and update status bar
            from expand_diplomatic.expander import is_page_xml
            fmt = "PAGE" if is_page_xml(text) else "TEI"
            self.format_label_var.set(fmt)
            _status(self, f"Loaded {p.name}")
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def _load_file(self, p: Path) -> None:
        """Load XML from path into input; clear output unless expanded file exists."""
        text = p.read_text(encoding="utf-8")
        self.input_txt.delete("1.0", tk.END)
        self.input_txt.insert("1.0", text)
        self.original_input = text
        self.last_input_path = p
        _block_ranges_cache = getattr(self, "_block_ranges_cache", None)
        if _block_ranges_cache is not None:
            _block_ranges_cache.clear()
        self._load_expanded_if_exists(p)
        # Detect format and update status bar
        from expand_diplomatic.expander import is_page_xml
        fmt = "PAGE" if is_page_xml(text) else "TEI"
        self.format_label_var.set(fmt)
        _status(self, f"Loaded {p.name}")

    def _load_expanded_if_exists(self, input_path: Path) -> None:
        """Clear output panel; if <stem>_expanded.xml exists, load it."""
        self._synced_block_idx = None
        self.output_txt.delete("1.0", tk.END)
        self.last_output_path = None
        expanded_path = input_path.parent / f"{input_path.stem}_expanded.xml"
        if expanded_path.exists():
            try:
                text = expanded_path.read_text(encoding="utf-8")
                self.output_txt.insert("1.0", text)
                self.output_txt.see("1.0")
                self.last_output_path = expanded_path
            except Exception:
                pass

    def _on_prev_file(self) -> None:
        """Load previous XML file in folder. Left arrow."""
        if not self.folder_files or self.folder_index <= 0:
            return
        self.folder_index -= 1
        try:
            self._load_file(self.folder_files[self.folder_index])
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def _on_next_file(self) -> None:
        """Load next XML file in folder. Right arrow."""
        if not self.folder_files or self.folder_index < 0 or self.folder_index >= len(self.folder_files) - 1:
            return
        self.folder_index += 1
        try:
            self._load_file(self.folder_files[self.folder_index])
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def _on_expand(self) -> None:
        backend = (self.backend_var.get() or "gemini").strip() or "gemini"
        if backend not in BACKENDS:
            backend = "gemini"
        self.backend = backend
        api_key = _resolve_api_key(self)
        xml = self.input_txt.get("1.0", tk.END)
        if not xml.strip():
            messagebox.showwarning("Expand", "Input is empty. Open an XML file or paste XML.")
            return
        if backend == "gemini" and not api_key:
            _show_api_error_dialog(self, "No API key set.", xml, is_retry=False)
            return
        
        # If expansion is running, toggle queue membership
        if self.expand_running:
            # Check if current file is already in queue
            current_path = self.last_input_path
            for i, job in enumerate(self._expand_queue):
                if job.get("path") == current_path:
                    # Remove from queue
                    self._expand_queue.pop(i)
                    self._update_queue_label()
                    _status(self, f"Removed from queue")
                    return
            # Not in queue, add it
            self._add_to_queue(xml, api_key, backend, self.last_input_path)
            return
        
        _run_expand_internal(self, xml, api_key, backend, retry=False)

    def _on_whole_doc_change(self, *args: object) -> None:
        """When user switches to Block-by-block during expansion, cancel and restart in block-by-block mode."""
        if not getattr(self, "expand_running", False):
            return
        if not self.whole_document_var.get():  # Switched to block-by-block
            self.cancel_requested = True
            self._restart_with_block_by_block = True

    def _on_reexpand(self) -> None:
        """Re-expand from original (single file) or re-run batch on same file list. Uses updated examples+learned."""
        # If batch list is visible, Re-expand = re-run batch on those files
        if getattr(self, "_batch_files", None) and len(self._batch_files) > 0:
            if self.expand_running:
                messagebox.showwarning("Re-expand", "Expansion in progress. Cancel or wait, then try Re-expand.")
                return
            try:
                parallel = int(self.concurrent_var.get().strip() or "2")
                parallel = max(1, min(8, parallel))
            except ValueError:
                parallel = 2
            model = self.gemini_model_var.get() if (self.backend_var.get() or "").strip() == "gemini" else ""
            if (self.backend_var.get() or "").strip() == "gemini" and "pro" in (model or "").lower():
                parallel = min(parallel, 2)
            self._batch_status = {f.name: "pending" for f in self._batch_files}
            self._update_batch_list()
            self._run_batch(self._batch_files, parallel)
            return

        xml = getattr(self, "original_input", "") or ""
        if not xml.strip():
            messagebox.showwarning("Re-expand", "No original. Open a file or run Expand first.")
            return
        self.input_txt.delete("1.0", tk.END)
        self.input_txt.insert("1.0", xml)
        backend = (self.backend_var.get() or "gemini").strip() or "gemini"
        if backend not in BACKENDS:
            backend = "gemini"
        self.backend = backend
        api_key = _resolve_api_key(self)
        if backend == "gemini" and not api_key:
            _show_api_error_dialog(self, "No API key set.", xml, is_retry=False)
            return

        # If expansion is running, add to queue (no toggle for re-expand)
        if self.expand_running:
            self._add_to_queue(xml, api_key, backend, self.last_input_path)
            return

        _run_expand_internal(self, xml, api_key, backend, retry=False)

    def _add_to_queue(self, xml: str, api_key: str | None, backend: str, path: Path | None = None) -> None:
        """Add an expansion job to the queue."""
        self._expand_queue.append({
            "xml": xml,
            "api_key": api_key,
            "backend": backend,
            "path": path,
        })
        self._update_queue_label()
        self._update_expand_button_text()

    def _process_next_in_queue(self) -> bool:
        """Process the next item in the queue. Returns True if there was an item to process."""
        if not self._expand_queue:
            self._update_queue_label()
            return False
        
        job = self._expand_queue.pop(0)
        self._update_queue_label()
        
        # Load the XML for the queued job
        xml = job["xml"]
        api_key = job["api_key"]
        backend = job["backend"]
        path = job.get("path")
        
        # Update input panel if path is available
        if path and path.exists():
            try:
                xml = path.read_text(encoding="utf-8")
                self.input_txt.delete("1.0", tk.END)
                self.input_txt.insert("1.0", xml)
                self.last_input_path = path
                self.original_input = xml
            except Exception:
                pass  # Use the saved XML if file read fails
        else:
            # Use the queued XML
            self.input_txt.delete("1.0", tk.END)
            self.input_txt.insert("1.0", xml)
        
        # Start expansion
        _run_expand_internal(self, xml, api_key, backend, retry=False)
        return True

    def _update_queue_label(self) -> None:
        """Update the queue status label and show/hide Clear Q button."""
        count = len(self._expand_queue)
        if count > 0:
            self._queue_label_var.set(f"Queue: {count}")
            self._clear_queue_btn.grid()  # Show Clear Q button
        else:
            self._queue_label_var.set("")
            self._clear_queue_btn.grid_remove()  # Hide Clear Q button
        self._update_expand_button_text()
    
    def _update_expand_button_text(self) -> None:
        """Update Expand button text to show queue count if running."""
        if not self.expand_running:
            self.expand_btn.config(text="Expand")
            return
        
        count = len(self._expand_queue)
        if count > 0:
            self.expand_btn.config(text=f"Queued ({count})")
        else:
            self.expand_btn.config(text="Queued")

    def _clear_queue(self) -> None:
        """Clear all queued expansions."""
        self._expand_queue.clear()
        self._update_queue_label()
        self._update_expand_button_text()
        _status(self, "Queue cleared")

    def _on_batch(self) -> None:
        """Open folder dialog and batch-expand all XML files in parallel."""
        # Validate API key for Gemini backend before folder selection
        backend = (self.backend_var.get() or "gemini").strip() or "gemini"
        api_key = _resolve_api_key(self)
        if backend == "gemini" and not api_key:
            messagebox.showerror(
                "No API key",
                "Gemini backend requires an API key.\n\n"
                "Set GEMINI_API_KEY in .env, or switch to Local backend.",
            )
            return

        folder = filedialog.askdirectory(
            title="Select folder with XML files",
            initialdir=str(self._file_dialog_dir()),
        )
        if not folder:
            return
        folder_path = Path(folder)
        files = sorted(folder_path.glob("*.xml"))
        files = [f for f in files if not f.stem.endswith("_expanded")]
        if not files:
            messagebox.showinfo("Batch", "No XML files found (excluding *_expanded.xml).")
            return

        # Ask for confirmation and parallel count
        try:
            parallel = int(self.concurrent_var.get().strip() or "2")
            parallel = max(1, min(8, parallel))
        except ValueError:
            parallel = 2
        # Pro models: cap parallel to 2 (slower, longer timeouts; reduces overload)
        model = self.gemini_model_var.get() if backend == "gemini" else ""
        if backend == "gemini" and "pro" in (model or "").lower():
            parallel = min(parallel, 2)

        # Show file list in confirmation
        file_list_preview = "\n".join(f"  • {f.name}" for f in files[:10])
        if len(files) > 10:
            file_list_preview += f"\n  … and {len(files) - 10} more"

        if not messagebox.askyesno(
            "Batch expand",
            f"Expand {len(files)} files in '{folder_path.name}'?\n\n"
            f"Files:\n{file_list_preview}\n\n"
            f"Parallel files: {parallel}\n"
            f"Backend: {backend}\n"
            f"Modality: {self.modality_var.get()}\n\n"
            "Output: <filename>_expanded.xml in same folder",
        ):
            return

        # Show batch panel and run
        self._show_batch_panel(files)
        self._run_batch(files, parallel)

    def _run_batch(self, files: list, parallel: int) -> None:
        """Run batch expansion in background with file status tracking."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        backend = (self.backend_var.get() or "gemini").strip() or "gemini"
        api_key = _resolve_api_key(self)
        modality = self.modality_var.get().strip() or "full"
        model = self.gemini_model_var.get() if backend == "gemini" else "llama3.2"

        examples_path = Path(self.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
        include_learned = bool(getattr(self, "include_learned_var", None) and self.include_learned_var.get())
        try:
            examples = load_examples(examples_path, include_learned=include_learned)
        except ValueError as e:
            messagebox.showerror("Examples", str(e))
            self._hide_batch_panel()
            return

        total = len(files)
        completed = [0]
        failed = []
        cancelled = [False]

        # Batch defaults to whole-doc (faster for many files)
        whole_doc = True
        ex_path = examples_path if (whole_doc and backend == "gemini" and not include_learned) else None

        def _is_timeout(e: BaseException) -> bool:
            if isinstance(e, TimeoutError):
                return True
            s = str(e).lower()
            return "timeout" in s or "timed out" in s

        def expand_one(f: Path) -> tuple[Path, bool, str]:
            # Mark as processing
            self.root.after(0, lambda: self._update_batch_file_status(f.name, "processing"))
            from expand_diplomatic.expander import expand_xml
            xml = f.read_text(encoding="utf-8")
            out_path = f.parent / f"{f.stem}_expanded.xml"
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    result = expand_xml(
                        xml, examples,
                        model=model,
                        api_key=api_key,
                        backend=backend,
                        modality=modality,
                        whole_document=whole_doc,
                        examples_path=ex_path,
                    )
                    out_path.write_text(result, encoding="utf-8")
                    return (f, True, f.name)
                except Exception as e:
                    if _is_timeout(e) and attempt < max_attempts - 1:
                        continue
                    return (f, False, f"{f.name}: {e}")

        def run_batch() -> None:
            nonlocal completed, failed, cancelled
            self.expand_running = True
            self.cancel_requested = False
            self.cancel_btn.config(state=tk.NORMAL)

            def on_done():
                self.expand_running = False
                self.cancel_btn.config(state=tk.DISABLED)
                try:
                    self.progress_bar.stop()
                except Exception:
                    pass
                self.progress_bar.configure(mode="determinate")
                self.progress_bar["value"] = 0
                # Final update to batch list
                self._update_batch_list()
                if cancelled[0]:
                    _status(self, f"Batch cancelled ({completed[0]}/{total} done)")
                    messagebox.showinfo("Batch cancelled", f"Stopped after {completed[0]} files.")
                elif failed:
                    _status(self, f"Batch done: {total - len(failed)}/{total} OK, {len(failed)} failed")
                    messagebox.showwarning("Batch complete", f"{len(failed)} files failed:\n\n" + "\n".join(failed[:10]))
                else:
                    _status(self, f"Batch done: {total} files expanded")
                    messagebox.showinfo("Batch complete", f"All {total} files expanded successfully.")
                # Auto-hide batch panel after 5 seconds if successful
                if not failed and not cancelled[0]:
                    self.root.after(5000, self._hide_batch_panel)

            try:
                with ThreadPoolExecutor(max_workers=parallel) as executor:
                    future_to_file = {executor.submit(expand_one, f): f for f in files}
                    for future in as_completed(future_to_file):
                        if getattr(self, "cancel_requested", False):
                            cancelled[0] = True
                            # Mark remaining as pending (not processed)
                            for fut, fpath in future_to_file.items():
                                if not fut.done():
                                    fut.cancel()
                            break
                        try:
                            f_path, ok, msg = future.result()
                        except Exception as e:
                            f_path = future_to_file[future]
                            ok, msg = False, str(e)
                        completed[0] += 1
                        # Update file status
                        status = "done" if ok else "failed"
                        self.root.after(0, lambda fn=f_path.name, s=status: self._update_batch_file_status(fn, s))
                        if not ok:
                            failed.append(msg)

                        def update_progress(c=completed[0], t=total, m=msg, o=ok):
                            pct = int(100 * c / t)
                            self.progress_bar["value"] = pct
                            status_msg = f"Batch: {c}/{t}"
                            if not o:
                                status_msg += f" (failed: {m[:30]})"
                            _status(self, status_msg)

                        self.root.after(0, update_progress)
            finally:
                self.root.after(0, on_done)

        _status(self, f"Batch: 0/{total}")
        try:
            self.progress_bar.stop()
        except Exception:
            pass
        self.progress_bar.configure(mode="determinate")
        self.progress_bar["value"] = 0
        t = threading.Thread(target=run_batch, daemon=True)
        t.start()

    def _on_cancel_expand(self) -> None:
        """Cancel the current expansion (signals worker to stop, resets UI)."""
        if not self.expand_running:
            return
        self.cancel_requested = True
        _stop_hang_check(self)
        self.expand_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        try:
            self.progress_bar.stop()
        except Exception:
            pass
        self.progress_bar.configure(mode="determinate")
        self.progress_bar["value"] = 0
        self.time_label_var.set("")
        _status(self, "Cancelling…")
        # Worker checks cancel_requested; on_done ignores result when cancelled.

    def _on_test_connection(self) -> None:
        api_key = _resolve_api_key(self)
        def run() -> None:
            from run_gemini import test_gemini_connection
            ok, msg = test_gemini_connection(api_key=api_key or None, timeout=15.0)

            def done() -> None:
                _status(self, "Idle")
                if ok:
                    messagebox.showinfo("Test connection", msg, parent=self.root)
                else:
                    messagebox.showerror("Test connection failed", msg, parent=self.root)

            self.root.after(0, done)

        _status(self, "Testing Gemini…")
        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _refresh_models_background(self) -> None:
        """Fetch Gemini models in background; update menu when done. No UI feedback (fast startup)."""
        api_key = _resolve_api_key(self)

        def run() -> None:
            from expand_diplomatic.gemini_models import get_available_models
            models = get_available_models(api_key=api_key, force_refresh=False)

            def done() -> None:
                global GEMINI_MODELS
                if models and models != GEMINI_MODELS:
                    GEMINI_MODELS = models
                    _apply_model_menu_labels(self._model_menu, self.gemini_model_var, models)
                    current = self.gemini_model_var.get()
                    if current not in models:
                        self.gemini_model_var.set(DEFAULT_GEMINI_MODEL if DEFAULT_GEMINI_MODEL in models else models[0])

            self.root.after(0, done)

        threading.Thread(target=run, daemon=True).start()

    def _on_refresh_models(self) -> None:
        """Refresh Gemini model list from API (manual, with feedback)."""
        api_key = _resolve_api_key(self)
        
        def run() -> None:
            from expand_diplomatic.gemini_models import get_available_models
            models = get_available_models(api_key=api_key, force_refresh=True)
            
            def done() -> None:
                global GEMINI_MODELS
                GEMINI_MODELS = models
                _apply_model_menu_labels(self._model_menu, self.gemini_model_var, models)
                # Ensure current selection is valid
                current = self.gemini_model_var.get()
                if current not in models:
                    self.gemini_model_var.set(DEFAULT_GEMINI_MODEL if DEFAULT_GEMINI_MODEL in models else models[0])
                _status(self, f"Models updated ({len(models)} available)")
                messagebox.showinfo("Model refresh", f"Found {len(models)} Gemini models", parent=self.root)
            
            self.root.after(0, done)
        
        _status(self, "Fetching models…")
        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _on_save(self) -> None:
        default_name = ""
        if self.last_input_path is not None:
            default_name = f"{self.last_input_path.stem}_expanded.xml"
        path = filedialog.asksaveasfilename(
            title="Save output",
            initialdir=str(self._file_dialog_dir()),
            initialfile=default_name,
            defaultextension=".xml",
            filetypes=[("XML", "*.xml"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(self.output_txt.get("1.0", tk.END), encoding="utf-8")
            self.last_dir = Path(path).parent
            _status(self, f"Saved {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _on_save_input_txt(self) -> None:
        """Extract text lines from input XML and save as .txt."""
        xml = self.input_txt.get("1.0", tk.END)
        if not xml.strip():
            messagebox.showwarning("Input→TXT", "Input is empty. Open an XML file first.")
            return
        default_name = ""
        if self.last_input_path is not None:
            default_name = f"{self.last_input_path.stem}.txt"
        path = filedialog.asksaveasfilename(
            title="Save input as text",
            initialdir=str(self._file_dialog_dir()),
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            from expand_diplomatic.expander import extract_text_lines
            text = extract_text_lines(xml)
            Path(path).write_text(text, encoding="utf-8")
            self.last_dir = Path(path).parent
            _status(self, f"Saved input lines: {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _on_save_output_txt(self) -> None:
        """Extract text lines from output XML and save as .txt."""
        xml = self.output_txt.get("1.0", tk.END)
        if not xml.strip():
            messagebox.showwarning("Output→TXT", "Output is empty. Run Expand first.")
            return
        default_name = ""
        if self.last_input_path is not None:
            default_name = f"{self.last_input_path.stem}_expanded.txt"
        path = filedialog.asksaveasfilename(
            title="Save output as text",
            initialdir=str(self._file_dialog_dir()),
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            from expand_diplomatic.expander import extract_text_lines
            text = extract_text_lines(xml)
            Path(path).write_text(text, encoding="utf-8")
            self.last_dir = Path(path).parent
            _status(self, f"Saved output lines: {Path(path).name}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _on_diff(self) -> None:
        """Show diff between input and output panels (diff input.xml output.xml style)."""
        inp = self.input_txt.get("1.0", tk.END)
        out = self.output_txt.get("1.0", tk.END)
        if not out.strip():
            messagebox.showwarning("Diff", "Output is empty. Run Expand first.")
            return
        inp_label = str(self.last_input_path) if self.last_input_path else "input.xml"
        out_label = str(self.last_output_path) if self.last_output_path else "output.xml"
        try:
            import difflib
            lines_inp = inp.splitlines(keepends=True)
            lines_out = out.splitlines(keepends=True)
            diff_lines = list(difflib.unified_diff(
                lines_inp, lines_out,
                fromfile=inp_label,
                tofile=out_label,
                lineterm="",
            ))
            diff_text = "".join(diff_lines) if diff_lines else "(no differences)"
        except Exception as e:
            diff_text = f"Diff failed: {e}"
        win = tk.Toplevel(self.root)
        win.title("Diff: input vs output")
        win.geometry("700x400")
        txt = scrolledtext.ScrolledText(win, font=("Courier", 9), wrap=tk.NONE)
        txt.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        txt.insert(tk.END, diff_text)
        txt.config(state=tk.DISABLED)
        _add_tooltip(txt, "diff input.xml output.xml — lines with - are input only, + are output only")

    def _on_browse_examples(self) -> None:
        path = filedialog.askopenfilename(
            title="Examples JSON",
            initialdir=str(self._file_dialog_dir()),
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if path:
            self.examples_var.set(path)
            self.last_dir = Path(path).parent
            self._refresh_train_list()

    def _schedule_train_refresh(self, *args: object) -> None:
        """Debounce Train list refresh so search typing doesn't reload on every keystroke."""
        if self._train_refresh_after_id is not None:
            self.root.after_cancel(self._train_refresh_after_id)
        self._train_refresh_after_id = self.root.after(150, self._do_train_refresh)

    def _do_train_refresh(self) -> None:
        self._train_refresh_after_id = None
        self._refresh_train_list()

    def _refresh_train_list(self) -> None:
        p = Path(self.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
        try:
            examples = load_examples(p)
        except ValueError as e:
            _status(self, str(e))
            examples = []
        search = (self._train_search_var.get() or "").strip().lower()
        total = len(examples)
        if search:
            examples = [
                e for e in examples
                if search in (e.get("diplomatic") or "").lower() or search in (e.get("full") or "").lower()
            ]
        self.train_list.config(state=tk.NORMAL)
        self.train_list.delete("1.0", tk.END)
        if search and total:
            self.train_list.insert(tk.END, f"  ({len(examples)} of {total} pairs)\n")
        for e in examples:
            self.train_list.insert(tk.END, f"  {e['diplomatic']!r} → {e['full']!r}\n")
        self.train_list.config(state=tk.DISABLED)

    def _selection_from(self, widget: tk.Text) -> str:
        try:
            return widget.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return ""

    def _on_dip_from_input(self) -> None:
        s = self._selection_from(self.input_txt)
        if s:
            self.dip_var.set(s)
            _status(self, "Diplomatic set from input selection")
        else:
            messagebox.showwarning("Train", "Select text in Input (left panel), then click From input.")

    def _on_full_from_output(self) -> None:
        s = self._selection_from(self.output_txt)
        if s:
            self.full_var.set(s)
            _status(self, "Full set from output selection")
        else:
            messagebox.showwarning("Train", "Select text in Output (right panel), then click From output.")

    def _on_add_example(self) -> None:
        d = self.dip_var.get().strip()
        f = self.full_var.get().strip()
        if not d or not f:
            messagebox.showwarning("Train", "Enter both Diplomatic and Full.")
            return
        p = Path(self.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
        try:
            examples = load_examples(p)
        except ValueError as e:
            messagebox.showerror("Examples", str(e))
            return
        examples.append({"diplomatic": d, "full": f})
        try:
            save_examples(p, examples)
        except Exception as e:
            messagebox.showerror("Save examples", str(e))
            return
        self.dip_var.set("")
        self.full_var.set("")
        self._refresh_train_list()
        _status(self, f"Added 1 pair → {p.name} ({len(examples)} total)")

    def _collect_preferences(self) -> dict:
        """Build preferences dict from current UI state."""
        p = {}
        try:
            p["backend"] = self.backend_var.get().strip() or "gemini"
            p["modality"] = self.modality_var.get().strip() or "full"
            p["gemini_model"] = self.gemini_model_var.get().strip() or ""
            p["concurrent"] = self.concurrent_var.get().strip() or "2"
            p["passes"] = self.passes_var.get().strip() or "1"
            p["whole_document"] = bool(self.whole_document_var.get())
            p["auto_learn"] = bool(self.auto_learn_var.get())
            p["include_learned"] = bool(self.include_learned_var.get())
            p["autosave"] = bool(self.autosave_var.get())
            p["examples_path"] = self.examples_var.get().strip() or ""
            if self.last_dir is not None and self.last_dir.exists():
                p["last_dir"] = str(self.last_dir)
        except Exception:
            pass
        return p

    def _apply_preferences(self, p: dict) -> None:
        """Apply loaded preferences to UI. Safe to call with empty dict."""
        if not p:
            return
        try:
            if p.get("backend") in BACKENDS:
                self.backend_var.set(p["backend"])
                self._on_backend_change(p["backend"])
            if p.get("modality") in MODALITIES:
                self.modality_var.set(p["modality"])
            gemini_model = p.get("gemini_model", "").strip()
            if gemini_model and gemini_model in GEMINI_MODELS:
                self.gemini_model_var.set(gemini_model)
            conc = p.get("concurrent", "")
            if conc and conc.isdigit():
                self.concurrent_var.set(conc)
            passes = p.get("passes", "")
            if passes and passes.isdigit():
                self.passes_var.set(passes)
            if "whole_document" in p:
                self.whole_document_var.set(bool(p["whole_document"]))
            if "auto_learn" in p:
                self.auto_learn_var.set(bool(p["auto_learn"]))
            if "include_learned" in p:
                self.include_learned_var.set(bool(p["include_learned"]))
            if "autosave" in p:
                self.autosave_var.set(bool(p["autosave"]))
            ex_path = p.get("examples_path", "").strip()
            if ex_path and Path(ex_path).exists():
                self.examples_var.set(ex_path)
                self._refresh_train_list()
            last_dir = p.get("last_dir", "")
            if last_dir:
                pd = Path(last_dir)
                if pd.is_dir():
                    self.last_dir = pd
        except Exception:
            pass

    def _on_quit(self) -> None:
        """Save preferences and close."""
        _save_preferences(self._collect_preferences())
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    """Entry point for expand-diplomatic-gui."""
    App().run()


if __name__ == "__main__":
    main()
