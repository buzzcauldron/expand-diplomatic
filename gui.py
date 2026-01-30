#!/usr/bin/env python3
"""
Minimal GUI for expand_diplomatic: input/output panels, Load / Expand / Save, train examples.
Requires tkinter (stdlib). Run: python gui.py
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext

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
from expand_diplomatic.examples_io import load_examples, save_examples

DEFAULT_EXAMPLES = ROOT_DIR / "examples.json"
BACKENDS = ("gemini", "local")
MODALITIES = ("full", "conservative", "normalize", "aggressive")


def _api_key_error_message() -> str:
    return (
        "GEMINI_API_KEY or GOOGLE_API_KEY is not set.\n\n"
        "1. Edit .env in the project root and add your key:\n"
        f"   {ENV_PATH}\n\n"
        "2. Set: GEMINI_API_KEY=your-key\n"
        "   (Get a key: https://aistudio.google.com/apikey)\n\n"
        "3. Restart the app."
    )


def _status(app: "App", msg: str) -> None:
    app.status_var.set(msg)
    app.root.update_idletasks()


def _resolve_api_key(app: "App") -> str | None:
    return app.session_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _expand_worker(
    xml: str,
    examples: list,
    api_key: str | None,
    app: "App",
    backend: str,
    model: str,
    modality: str,
) -> None:
    from expand_diplomatic.expander import expand_xml

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
        )
    except Exception as e:
        err = e

    def on_done() -> None:
        app.expand_btn.config(state=tk.NORMAL)
        if err is not None:
            _status(app, "Idle")
            _show_api_error_dialog(app, str(err), xml, is_retry=True)
            return
        app.output_txt.delete("1.0", tk.END)
        app.output_txt.insert("1.0", result or "")
        _status(app, "Done.")

    app.root.after(0, on_done)


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
    examples_path = Path(app.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
    examples = load_examples(examples_path)
    if not retry:
        if not xml.strip():
            messagebox.showwarning("Expand", "Input is empty. Open an XML file or paste XML.")
            return
        if not examples and not messagebox.askyesno("No examples", "No examples loaded. Add pairs in Train or use examples.json. Continue anyway?"):
            return
    model = app.model_gemini if backend == "gemini" else app.model_local
    modality = app.modality_var.get().strip() or "full"
    if modality not in MODALITIES:
        modality = "full"
    _status(app, "Expanding…")
    app.expand_btn.config(state=tk.DISABLED)
    app.last_expand_xml = xml
    app.last_expand_api_key = api_key
    app.last_expand_backend = backend
    app.last_expand_model = model
    t = threading.Thread(
        target=_expand_worker,
        args=(xml, examples, api_key, app, backend, model, modality),
        daemon=True,
    )
    t.start()


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Expand diplomatic")
        self.root.minsize(600, 400)
        self.root.geometry("900x550")

        self.status_var = tk.StringVar(value="Idle")
        self.examples_var = tk.StringVar(value=str(DEFAULT_EXAMPLES))
        self.expand_btn: tk.Button = None  # set later
        self._font = ("Courier", 10)
        self._font_sm = ("Courier", 9)
        self.session_api_key: str | None = None
        self.backend: str = "gemini"
        self.model_gemini: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
        self.model_local: str = "llama3.2"
        self.last_expand_xml = ""
        self.last_expand_api_key: str | None = None
        self.last_expand_backend = "gemini"
        self.last_expand_model = "gemini-2.5-pro"
        self.last_dir: Path | None = None  # last Open/Save directory, for file dialogs
        self.backend_var = tk.StringVar(value="gemini")
        self.modality_var = tk.StringVar(value="full")

        self._build_toolbar()
        self._build_main()
        self._build_train()
        self._build_status()

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, relief=tk.RAISED, bd=1)
        bar.pack(side=tk.TOP, fill=tk.X, padx=2, pady=2)
        tk.Button(bar, text="Open…", command=self._on_open).pack(side=tk.LEFT, padx=2, pady=2)
        self.expand_btn = tk.Button(bar, text="Expand", command=self._on_expand)
        self.expand_btn.pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(bar, text="Save…", command=self._on_save).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Label(bar, text="Backend:").pack(side=tk.LEFT, padx=(8, 0), pady=2)
        tk.OptionMenu(bar, self.backend_var, *BACKENDS).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Label(bar, text="Modality:").pack(side=tk.LEFT, padx=(8, 0), pady=2)
        tk.OptionMenu(bar, self.modality_var, *MODALITIES).pack(side=tk.LEFT, padx=2, pady=2)
        tk.Label(bar, text="Examples:").pack(side=tk.LEFT, padx=(8, 0), pady=2)
        ex = tk.Entry(bar, textvariable=self.examples_var, width=32)
        ex.pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(bar, text="…", width=2, command=self._on_browse_examples).pack(side=tk.LEFT, padx=0, pady=2)
        tk.Button(bar, text="Refresh", command=self._refresh_train_list).pack(side=tk.LEFT, padx=2, pady=2)

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

    def _build_train(self) -> None:
        tr = tk.LabelFrame(self.root, text="Train (add examples)")
        tr.pack(side=tk.TOP, fill=tk.X, padx=4, pady=2)
        row = tk.Frame(tr)
        row.pack(fill=tk.X, padx=2, pady=2)
        tk.Label(row, text="Diplomatic:").pack(side=tk.LEFT, padx=2)
        self.dip_var = tk.StringVar()
        tk.Entry(row, textvariable=self.dip_var, width=24).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        tk.Label(row, text="Full:").pack(side=tk.LEFT, padx=(8, 2))
        self.full_var = tk.StringVar()
        tk.Entry(row, textvariable=self.full_var, width=24).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        tk.Button(row, text="Add", command=self._on_add_example).pack(side=tk.LEFT, padx=4)
        self.train_list = scrolledtext.ScrolledText(tr, height=3, wrap=tk.WORD, state=tk.DISABLED, font=self._font_sm)
        self.train_list.pack(fill=tk.X, padx=2, pady=2)
        self._refresh_train_list()

    def _build_status(self) -> None:
        tk.Label(self.root, textvariable=self.status_var, anchor=tk.W).pack(
            side=tk.BOTTOM, fill=tk.X, padx=4, pady=2
        )

    def _file_dialog_dir(self) -> Path:
        """Directory to use as initialdir for Open/Save/browse dialogs."""
        d = self.last_dir
        if d is not None and d.is_dir():
            return d
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
            text = Path(path).read_text(encoding="utf-8")
            self.input_txt.delete("1.0", tk.END)
            self.input_txt.insert("1.0", text)
            self.last_dir = Path(path).parent
            _status(self, f"Loaded {Path(path).name}")
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

    def _on_save(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save output",
            initialdir=str(self._file_dialog_dir()),
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
        examples = load_examples(p)
        self.train_list.config(state=tk.NORMAL)
        self.train_list.delete("1.0", tk.END)
        for e in examples:
            self.train_list.insert(tk.END, f"  {e['diplomatic']!r} → {e['full']!r}\n")
        self.train_list.config(state=tk.DISABLED)

    def _on_add_example(self) -> None:
        d = self.dip_var.get().strip()
        f = self.full_var.get().strip()
        if not d or not f:
            messagebox.showwarning("Train", "Enter both Diplomatic and Full.")
            return
        p = Path(self.examples_var.get().strip() or str(DEFAULT_EXAMPLES))
        examples = load_examples(p)
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


if __name__ == "__main__":
    App().run()
