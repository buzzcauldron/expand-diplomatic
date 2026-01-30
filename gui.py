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


def _ensure_env() -> None:
    """Create .env from .env.example if missing; then load .env."""
    if not ENV_PATH.exists() and ENV_EXAMPLE.exists():
        import shutil

        shutil.copy(ENV_EXAMPLE, ENV_PATH)
    load_dotenv(ENV_PATH)


_ensure_env()

# Lightweight imports only at startup (no run_gemini, lxml); expand_xml lazy-loaded on first Expand
from expand_diplomatic.examples_io import add_learned_pairs, get_learned_path, load_examples, save_examples

DEFAULT_EXAMPLES = ROOT_DIR / "examples.json"
BACKENDS = ("gemini", "local")
MODALITIES = ("full", "conservative", "normalize", "aggressive", "local")
GEMINI_MODELS = (
    "gemini-2.5-flash",       # Best price-performance (default)
    "gemini-2.0-flash",       # Fast, good quality
    "gemini-2.5-flash-lite",  # Fastest, most cost-efficient
    "gemini-3-flash-preview", # Latest Flash
    "gemini-2.5-pro",         # Pro (stable)
    "gemini-3-pro-preview",   # Pro 3
)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def _status(app: "App", msg: str) -> None:
    app.status_var.set(msg)
    app.root.update_idletasks()


def _resolve_api_key(app: "App") -> str | None:
    return app.session_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _show_pending_partial(app: "App") -> None:
    """Display queued partial result with stream delay for visible progress."""
    app.partial_display_after_id = None
    if app.pending_partial is not None:
        app.output_txt.delete("1.0", tk.END)
        app.output_txt.insert("1.0", app.pending_partial)
        app.output_txt.see(tk.END)
        app.pending_partial = None


def _schedule_auto_learn(
    app: "App",
    xml_input: str,
    xml_output: str,
    examples_path: Path,
) -> None:
    """Run auto-learn in a background thread when model is idle."""
    def learn() -> None:
        try:
            from expand_diplomatic.expander import extract_expansion_pairs

            pairs = extract_expansion_pairs(xml_input, xml_output)
            if not pairs:
                return
            learned_path = get_learned_path(examples_path)
            add_learned_pairs(pairs, learned_path)
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
        s = f"Expanding… block {current}/{total}" if total > 0 else "Expanding…"
        pct = int(100 * current / total) if total > 0 else 0

        def update_ui() -> None:
            app.last_progress_time = time.time()
            _status(app, s)
            app.progress_bar["value"] = pct
            # Show elapsed time
            elapsed = int(time.time() - app.expand_start_time)
            app.time_label_var.set(f"{elapsed}s")

        app.root.after(0, update_ui)

    def partial_cb(xml_result: str) -> None:
        """Stream each block's result; pace updates for visible real-time progress."""
        try:
            delay = max(0, min(300, int(app.stream_delay_var.get().strip() or "0")))
        except (ValueError, AttributeError):
            delay = 0
        app.pending_partial = xml_result
        if app.partial_display_after_id is not None:
            try:
                app.root.after_cancel(app.partial_display_after_id)
            except Exception:
                pass
        if delay <= 0:
            app.root.after(0, lambda: _show_pending_partial(app))
        else:
            app.partial_display_after_id = app.root.after(delay, lambda: _show_pending_partial(app))

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
        )
    except Exception as e:
        err = e

    def on_done() -> None:
        from run_gemini import format_api_error

        if app.partial_display_after_id is not None:
            try:
                app.root.after_cancel(app.partial_display_after_id)
            except Exception:
                pass
            app.partial_display_after_id = None
        app.pending_partial = None
        app.expand_btn.config(state=tk.NORMAL)
        app.progress_bar["value"] = 0
        app.time_label_var.set("")
        app.cancel_btn.config(state=tk.DISABLED)
        _stop_hang_check(app)
        if getattr(app, "expand_run_id", -1) != run_id:
            return
        if err is not None:
            if isinstance(err, ExpandCancelled):
                _status(app, "Cancelled.")
                return
            _status(app, "Idle")
            msg = format_api_error(err) if err else "Unknown error"
            _show_api_error_dialog(app, msg, xml, is_retry=True)
            return
        app.output_txt.delete("1.0", tk.END)
        app.output_txt.insert("1.0", result or "")
        elapsed = int(time.time() - app.expand_start_time)
        _status(app, f"Done in {elapsed}s.")
        # Auto-learn: quietly train local model on Gemini results in background
        if backend == "gemini" and getattr(app, "auto_learn_var", None) and app.auto_learn_var.get():
            ex_path = Path(app.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
            _schedule_auto_learn(app, xml, result or "", ex_path)

    app.root.after(0, on_done)


def _start_hang_check(app: "App") -> None:
    """Start periodic hang check during expansion."""
    HANG_THRESHOLD_SEC = 90
    CHECK_INTERVAL_MS = 5000  # Check every 5s

    def check() -> None:
        if not app.expand_running:
            return
        elapsed_since_progress = time.time() - app.last_progress_time
        total_elapsed = int(time.time() - app.expand_start_time)
        # Update elapsed time display
        app.time_label_var.set(f"{total_elapsed}s")
        if elapsed_since_progress > HANG_THRESHOLD_SEC:
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
        app.backend_var.set(app.last_expand_backend)
        app.backend = app.last_expand_backend
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
        _run_expand_internal(app, xml, None, "local", retry=True)

    def use_online() -> None:
        _close_error_dialog(win, app, focus_main=False)
        _focus_main(app)
        app.backend = "gemini"
        app.backend_var.set("gemini")
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
    # "Use learned": include learned_examples.json in the prompt when checked (any backend).
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
    if backend != "local":
        app.expand_btn.config(state=tk.DISABLED)
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
    app.progress_bar["value"] = 0
    app.cancel_btn.config(state=tk.NORMAL)
    _start_hang_check(app)
    run_id = app.expand_run_id
    t = threading.Thread(
        target=_expand_worker,
        args=(xml, examples, api_key, app, backend, model, modality, max_concurrent, passes, run_id),
        daemon=True,
    )
    t.start()


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        from expand_diplomatic._version import __version__
        self.root.title(f"Expand diplomatic v{__version__}")
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
        self._font = ("Courier", 10)
        self._font_sm = ("Courier", 9)
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
        self.folder_files: list[Path] = []  # XML files in current folder for Prev/Next
        self.folder_index: int = -1
        self.backend_var = tk.StringVar(value="gemini")
        self.modality_var = tk.StringVar(value="full")
        self.gemini_model_var = tk.StringVar(value=self.model_gemini)
        self.time_label_var = tk.StringVar(value="")
        # Progress/hang tracking
        self.progress_bar: ttk.Progressbar = None  # set in _build_status
        self.expand_start_time: float = 0.0
        self.last_progress_time: float = 0.0
        self.expand_running: bool = False
        self.hang_check_id: str | None = None
        self.auto_learn_var = tk.BooleanVar(value=True)
        self.include_learned_var = tk.BooleanVar(value=False)
        self.autosave_var = tk.BooleanVar(value=True)
        self.autosave_after_id: str | None = None
        self.autosave_idle_ms = 3000
        self.stream_delay_var = tk.StringVar(value="80")
        self.pending_partial: str | None = None
        self.partial_display_after_id: str | None = None
        self.image_path: Path | None = None
        self._image_photo: tk.PhotoImage | None = None
        self._image_panel_expanded = False

        self._build_toolbar()
        self._build_main()
        self._build_train()
        self._build_status()

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, relief=tk.RAISED, bd=1)
        self._toolbar_frame = bar
        bar.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)
        pad = dict(padx=1, pady=1)
        opts = {"font": ("", 8), "takefocus": True}
        # Row 0: Primary actions
        r1 = tk.Frame(bar)
        r1.pack(side=tk.TOP, fill=tk.X)
        c = 0
        for w in [
            (tk.Button, "Open", self._on_open, {"width": 4}),
            (tk.Button, "Expand", self._on_expand, {"width": 5}),
            (tk.Button, "Re-expand", self._on_reexpand, {"width": 8}),
            (tk.Button, "Save", self._on_save, {"width": 4}),
            (tk.Button, "◀", self._on_prev_file, {"width": 2}),
            (tk.Button, "▶", self._on_next_file, {"width": 2}),
            (tk.Button, "In→TXT", self._on_save_input_txt, {"width": 5}),
            (tk.Button, "Out→TXT", self._on_save_output_txt, {"width": 6}),
        ]:
            cls, txt, cmd, kw = w
            btn = cls(r1, text=txt, command=cmd, **{**pad, **kw})
            btn.pack(side=tk.LEFT, **pad)
            if txt == "Expand":
                self.expand_btn = btn
        # Row 1: Settings (grid so Examples entry expands)
        r2 = tk.Frame(bar)
        r2.pack(side=tk.TOP, fill=tk.X)
        r2.columnconfigure(16, weight=1, minsize=80)  # Examples entry expands
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
        col += 1
        tk.Label(r2, text="Mod", **opts).grid(row=0, column=col, **pad)
        col += 1
        tk.OptionMenu(r2, self.modality_var, *MODALITIES).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Label(r2, text="∥", **opts).grid(row=0, column=col, **pad)
        col += 1
        self.concurrent_var = tk.StringVar(value="2")
        tk.Spinbox(r2, from_=1, to=8, width=2, textvariable=self.concurrent_var).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Label(r2, text="Pass", **opts).grid(row=0, column=col, **pad)
        col += 1
        self.passes_var = tk.StringVar(value="1")
        tk.Spinbox(r2, from_=1, to=5, width=2, textvariable=self.passes_var).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Checkbutton(r2, text="Learn", variable=self.auto_learn_var, **opts).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Checkbutton(r2, text="Learned", variable=self.include_learned_var, **opts).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Checkbutton(r2, text="Auto", variable=self.autosave_var, **opts).grid(row=0, column=col, sticky=tk.W, **pad)
        col += 1
        tk.Label(r2, text="Stream", **opts).grid(row=0, column=col, **pad)
        col += 1
        tk.Spinbox(r2, from_=0, to=300, width=3, textvariable=self.stream_delay_var).grid(row=0, column=col, sticky=tk.W, **pad)
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

    def _on_backend_change(self, backend: str) -> None:
        """Show or hide Gemini model dropdown based on backend."""
        if backend.strip().lower() == "local":
            self._model_label.grid_remove()
            self._model_menu.grid_remove()
        else:
            self._model_label.grid()
            self._model_menu.grid()

    def _build_main(self) -> None:
        panes = tk.Frame(self.root)
        panes.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=2)
        left = tk.LabelFrame(panes, text="Input (XML)")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        opts = {"wrap": tk.WORD, "font": self._font}
        self.input_txt = scrolledtext.ScrolledText(left, **opts)
        self.input_txt.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        right = tk.LabelFrame(panes, text="Output (expanded)")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.output_txt = scrolledtext.ScrolledText(right, **opts)
        self.output_txt.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.input_txt.bind("<Button-1>", self._on_panel_click)
        self.output_txt.bind("<Button-1>", self._on_panel_click)
        self.input_txt.bind("<Double-Button-1>", self._on_panel_double_click)
        self.output_txt.bind("<Double-Button-1>", self._on_panel_double_click)
        self.input_txt.bind("<KeyRelease>", self._on_input_activity)

        # Third panel: image (collapsible, collapsed by default)
        self._image_right = tk.Frame(panes)
        self._image_right.pack(side=tk.LEFT, fill=tk.BOTH, padx=2)
        self._image_collapsed_strip = tk.Frame(self._image_right, width=28, bg="SystemButtonFace")
        self._image_collapsed_strip.pack(side=tk.LEFT, fill=tk.Y, padx=0, pady=0)
        self._image_collapsed_strip.pack_propagate(False)
        tk.Button(
            self._image_collapsed_strip, text="🖼\n▶", font=("", 9), width=3,
            command=self._toggle_image_panel,
        ).pack(fill=tk.BOTH, expand=True)
        self._image_panel = tk.LabelFrame(self._image_right, text="Image")
        img_header = tk.Frame(self._image_panel)
        img_header.pack(fill=tk.X, padx=2, pady=2)
        tk.Button(img_header, text="Upload…", command=self._on_upload_image, width=8).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(img_header, text="◀", width=2, command=self._toggle_image_panel).pack(side=tk.LEFT)
        self._image_canvas = tk.Canvas(self._image_panel, bg="gray90", highlightthickness=0)
        self._image_canvas.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self._image_canvas.bind("<Configure>", self._on_image_canvas_configure)
        self._image_panel.configure(width=280)
        self._image_panel.pack_propagate(True)

    def _toggle_image_panel(self) -> None:
        """Expand or collapse the image panel."""
        if self._image_panel_expanded:
            self._image_panel.pack_forget()
            self._image_collapsed_strip.pack(side=tk.LEFT, fill=tk.Y, padx=0, pady=0)
            self._image_panel_expanded = False
        else:
            self._image_collapsed_strip.pack_forget()
            self._image_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0, pady=0)
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
        """Save input to file when idle. Uses last_input_path or autosave.xml."""
        if not getattr(self, "autosave_var", None) or not self.autosave_var.get():
            return
        if self.expand_running:
            return
        xml = self.input_txt.get("1.0", tk.END)
        if not xml.strip():
            return
        path = getattr(self, "last_input_path", None)
        if path is None:
            base = self._file_dialog_dir()
            path = base / "autosave.xml"
            self.last_input_path = path
            self.last_dir = base
        try:
            path.write_text(xml, encoding="utf-8")
            _status(self, f"Autosaved {path.name}")
        except Exception:
            pass

    def _build_train(self) -> None:
        tr = tk.LabelFrame(self.root, text="Train (add examples)")
        tr.pack(side=tk.TOP, fill=tk.X, padx=4, pady=2)
        row = tk.Frame(tr)
        row.pack(fill=tk.X, padx=2, pady=2)
        row.columnconfigure(1, weight=1)  # Diplomatic entry
        row.columnconfigure(4, weight=1)  # Full entry
        tk.Label(row, text="Diplomatic:").grid(row=0, column=0, sticky=tk.W, padx=(0, 2), pady=2)
        self.dip_var = tk.StringVar()
        dip_entry = tk.Entry(row, textvariable=self.dip_var)
        dip_entry.grid(row=0, column=1, sticky=tk.EW, padx=2, pady=2)
        tk.Button(row, text="From input", command=self._on_dip_from_input, width=8).grid(row=0, column=2, padx=2, pady=2)
        tk.Label(row, text="Full:").grid(row=0, column=3, sticky=tk.W, padx=(8, 2), pady=2)
        self.full_var = tk.StringVar()
        full_entry = tk.Entry(row, textvariable=self.full_var)
        full_entry.grid(row=0, column=4, sticky=tk.EW, padx=2, pady=2)
        tk.Button(row, text="From output", command=self._on_full_from_output, width=9).grid(row=0, column=5, padx=2, pady=2)
        add_btn = tk.Button(row, text="Add pair", command=self._on_add_example, width=8)
        add_btn.grid(row=0, column=6, padx=4, pady=2)
        def _add_on_ctrl_return(_e) -> str:
            self._on_add_example()
            return "break"

        for w in (dip_entry, full_entry):
            w.bind("<Control-Return>", _add_on_ctrl_return)
        self.train_list = scrolledtext.ScrolledText(tr, height=3, wrap=tk.WORD, state=tk.DISABLED, font=self._font_sm)
        self.train_list.pack(fill=tk.X, padx=2, pady=2)
        self._refresh_train_list()

    def _build_status(self) -> None:
        status_frame = tk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=2)
        status_frame.columnconfigure(1, weight=1)
        tk.Label(status_frame, textvariable=self.status_var, anchor=tk.W).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8), pady=2
        )
        self.progress_bar = ttk.Progressbar(
            status_frame, orient=tk.HORIZONTAL, mode="determinate"
        )
        self.progress_bar.grid(row=0, column=1, sticky=tk.EW, padx=4, pady=2)
        tk.Label(status_frame, textvariable=self.time_label_var, width=6, anchor=tk.W).grid(
            row=0, column=2, sticky=tk.W, padx=4, pady=2
        )
        self.cancel_btn = tk.Button(
            status_frame, text="Cancel", command=self._on_cancel_expand, state=tk.DISABLED
        )
        self.cancel_btn.grid(row=0, column=3, padx=4, pady=2)

    def _on_panel_click(self, event: tk.Event) -> None:
        """On click in input or output, select the parallel block in the other panel."""
        widget = event.widget
        try:
            idx = widget.index(f"@{event.x},{event.y}")
        except Exception:
            return
        if not idx:
            return
        content = widget.get("1.0", tk.END)
        try:
            char_offset = widget.count("1.0", idx, "chars")[0]
        except Exception:
            return
        from expand_diplomatic.expander import get_block_ranges
        ranges = get_block_ranges(content)
        block_idx = None
        for i, (start, end) in enumerate(ranges):
            if start <= char_offset < end:
                block_idx = i
                break
        if block_idx is None:
            return
        other = self.output_txt if widget is self.input_txt else self.input_txt
        other_content = other.get("1.0", tk.END)
        other_ranges = get_block_ranges(other_content)
        if block_idx >= len(other_ranges):
            return
        start, end = other_ranges[block_idx]
        start_idx = other.index(f"1.0 + {start} chars")
        end_idx = other.index(f"1.0 + {end} chars")
        other.tag_remove("sel", "1.0", tk.END)
        other.tag_add("sel", start_idx, end_idx)
        other.mark_set("insert", start_idx)
        other.see(start_idx)

    def _on_panel_double_click(self, event: tk.Event) -> None:
        """On double-click, snap selection to the entire block at clicked position in both panels."""
        widget = event.widget
        try:
            idx = widget.index(f"@{event.x},{event.y}")
        except Exception:
            return
        if not idx:
            return
        content = widget.get("1.0", tk.END)
        try:
            char_offset = widget.count("1.0", idx, "chars")[0]
        except Exception:
            return
        from expand_diplomatic.expander import get_block_ranges
        ranges = get_block_ranges(content)
        block_idx = None
        for i, (start, end) in enumerate(ranges):
            if start <= char_offset < end:
                block_idx = i
                break
        if block_idx is None:
            return
        # Select full block in clicked widget
        start, end = ranges[block_idx]
        start_idx = widget.index(f"1.0 + {start} chars")
        end_idx = widget.index(f"1.0 + {end} chars")
        widget.tag_remove("sel", "1.0", tk.END)
        widget.tag_add("sel", start_idx, end_idx)
        widget.mark_set("insert", start_idx)
        widget.see(start_idx)
        # Sync selection to corresponding block in other panel
        other = self.output_txt if widget is self.input_txt else self.input_txt
        other_content = other.get("1.0", tk.END)
        other_ranges = get_block_ranges(other_content)
        if block_idx < len(other_ranges):
            o_start, o_end = other_ranges[block_idx]
            o_start_idx = other.index(f"1.0 + {o_start} chars")
            o_end_idx = other.index(f"1.0 + {o_end} chars")
            other.tag_remove("sel", "1.0", tk.END)
            other.tag_add("sel", o_start_idx, o_end_idx)
            other.mark_set("insert", o_start_idx)
            other.see(o_start_idx)
        return "break"  # Prevent default word selection

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
            _status(self, f"Loaded {p.name}")
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    def _load_file(self, p: Path) -> None:
        """Load XML from path into input."""
        text = p.read_text(encoding="utf-8")
        self.input_txt.delete("1.0", tk.END)
        self.input_txt.insert("1.0", text)
        self.original_input = text
        self.last_input_path = p
        _status(self, f"Loaded {p.name}")

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
        _run_expand_internal(self, xml, api_key, backend, retry=False)

    def _on_reexpand(self) -> None:
        """Re-expand from original file; show original on left, new result on right. Uses updated examples+learned."""
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
        _run_expand_internal(self, xml, api_key, backend, retry=False)

    def _on_cancel_expand(self) -> None:
        """Cancel the current expansion (signals worker to stop, resets UI)."""
        if not self.expand_running:
            return
        self.cancel_requested = True
        _stop_hang_check(self)
        self.expand_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
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

    def _refresh_train_list(self) -> None:
        p = Path(self.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
        try:
            examples = load_examples(p)
        except ValueError as e:
            _status(self, str(e))
            examples = []
        self.train_list.config(state=tk.NORMAL)
        self.train_list.delete("1.0", tk.END)
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

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    """Entry point for expand-diplomatic-gui."""
    App().run()


if __name__ == "__main__":
    main()
