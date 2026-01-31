# Windows Stability

## Platform-aware paths

- **Preferences** (`preferences.json`): `%APPDATA%\expand_diplomatic\` on Windows; `~/.config/expand_diplomatic/` elsewhere.
- **Gemini model cache**: `%LOCALAPPDATA%\expand_diplomatic\gemini_models.txt` on Windows; `~/.cache/expand_diplomatic/` elsewhere.

## Fonts

- Windows: `Courier New` (native monospace).  
- macOS/Linux: `Courier`.

## Process title

- `setproctitle` is optional. Failures (e.g. on Windows) are caught and ignored.

## GPU detection

- AC power: uses `GetSystemPowerStatus` on Windows.
- NVIDIA: `nvidia-smi` (if installed).
- AMD/Linux sysfs: not used on Windows.

## Path handling

- All file paths use `pathlib.Path`.
- `Path.home()` and env vars (`APPDATA`, `LOCALAPPDATA`) are used for config/cache.
- Tkinter `filedialog` paths are normalized via `Path()`.

## Threading

- GUI updates run on the main thread via `root.after(0, callback)`.
- Workers run in daemon threads.

## Encoding

- Files are read/written as UTF-8.
