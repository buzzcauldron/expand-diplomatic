# Changelog

All notable changes to this project will be documented in this file.

The project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (semver).

## [Unreleased]

## [0.3.4] - 2025-02-04

### Added

- **Review learned panel** (staged pairs): when Learn is on and Gemini is used, new pairs are staged for review instead of auto-added. Accept (to personal learned), Promote (to project examples), Reject (with short cooldown), Edit, Save edits, Accept all, Reject all, Export. Pairs already in the effective rules (project + learned + personal, per Layered Training) are not suggested again.
- **Eval subcommand**: `python -m expand_diplomatic eval --corpus-dir PATH --out-dir PATH` to compare rules-only, local (Ollama), and Gemini outputs and write a report.
- **Backend "rules"**: CLI and expander support `--backend rules` for expansion using only example pairs (no API, no Ollama).
- **Prompt budget**: GUI **Max ex** and **Strategy** (longest-first / most-recent); CLI `--max-examples` and `--example-strategy` to cap examples per prompt.
- **Personal vs project learned**: personal learned stored in config directory; **Promote** in Review adds to project `examples.json`; Layered Training uses both with project taking precedence.

### Changed

- **Status bar**: Hidden at startup; shown when user first clicks Expand and stays visible for the session.
- **Mouse wheel**: Scroll works in all panels and dialogs (MouseWheel, Button-4/5); toolbar button spacing increased (pad and separators) so labels are less cramped.
- **Review list**: Single Accept or Reject keeps selection and scroll position on the next item (no jump to top).
- **Staging filter**: Auto-learn does not suggest pairs that already exist in the effective rules (same layers as expand uses).
- **README**: Documented Review learned, eval subcommand, --max-examples/--example-strategy, --backend rules, train/eval subcommands, personal vs project learned, status bar, Max ex/Strategy in settings.
- **.env save path**: When the app is run as an installed package (e.g. system pip), "Save to .env" writes to the user config directory instead of site-packages, avoiding permission denied.
- **Focus during expand**: Highlighted (synced) block stays in view in both panels as partial results arrive and when expansion finishes; output and input scroll to keep the block visible.
- **Double-click / click alignment**: Single-click and double-click scroll both panels so the corresponding blocks are at the same vertical position (parallel); new _scroll_line_to_top helper.
- **Resizable dialogs**: Diff, Edit pair, Yes/No, API key, and error dialogs are resizable in height and width with sensible minsize.
- **Middle paned**: Vertical and horizontal PanedWindow sash show handle and (vertical) wider sash so the middle/content area can be resized easily.

## [0.3.3] - 2025-01-30

### Added

- **Windows .bat wrappers**: `scripts/build-windows-zip.bat` and `scripts/build-windows-msi.bat` for Command Prompt/PowerShell. Detect Git for Windows (bash); if missing, attempt `winget install Git.Git` or prompt to install from git-scm.com. Clear error if user double-clicks a `.sh` file (tell them to run the `.bat` or use Git Bash).

### Changed

- **Windows build docs**: README and BUILDING.md recommend running `scripts\build-windows-zip.bat` (and MSI `.bat`) on Windows instead of `.sh`; warn not to double-click `.sh` files. `.sh` script headers note to use the `.bat` on Windows.

## [0.3.2] - 2025-01-30

### Added

- **Project purpose rule** (`.cursor/rules/project-purpose.mdc`): expand Latin manuscript abbreviations into full Latin words for highly accurate transcripts; training pairs as ground truth; output stays in Latin
- **Learn: huge weight on local pairs**: when Learn is ticked and Gemini is used to expand, auto-learn adds Gemini-derived pairs to `learned_examples.json` but **never overwrites** diplomatic forms that exist in main examples (examples.json). Local/curated pairs are ground truth; only engage when Learn is ticked
- **gra → gratia** in examples.json; rules engine avoids replacing "gra" inside "gratia" (prefix guard) so plain "gra" expands correctly without corrupting existing "gratia"
- Toolbar **essential row** (Open, Expand, Re-expand, Save, ◀ ▶) stays visible when window is narrow; secondary row (Batch, In→TXT, Out→TXT, Diff + settings) scrolls horizontally

### Changed

- **GUI consistent basic design**: flat frames (no raised/sunken borders), font 9 for labels/buttons, unified padding; Input/Output panel titles shortened; Train label "Diplomatic" (was "Dip."); Train buttons In/Out/Add; Batch toggle "▶"/"▼" only; image strip arrow-only (▶/▼), Add button, no picture icon; narrow Search bar (width 14)
- **Docstrings**: package and expander state purpose (Latin manuscript abbreviations → full Latin words; training pairs ground truth; output in Latin)
- **local_llm**: skip pairs with empty full (never replace with empty); ground-truth post-pass documented; local modality prompt says training pairs are ground truth
- **add_learned_pairs**: optional `local_diplomatic` set — diplomatic forms from main examples are never overwritten by new (Gemini) guesses; used when Learn is ticked for aggressive training with huge weight on local pairs
- Toolbar scroll and Train search refresh throttled/debounced (50 ms and 150 ms)

### Fixed

- gratia / et cetera not expanding when source used different Unicode form (NFC/NFD); rules normalize before replace (0.3.1). 0.3.2: plain "gra" now expands to "gratia" without corrupting word "gratia" (prefix guard in rules)

## [0.3.1] - 2025-01-30

### Added

- Search filter for Train (examples) list: type in Search box to filter pairs by diplomatic or full text; shows "N of M pairs" when filtered

### Changed

- Image panel moved from side to top of window (horizontal strip when collapsed)
- Rule-based expansion: text and diplomatic keys normalized to NFC so forms like gratia and et cetera match regardless of Unicode encoding (e.g. NFD `grã` vs precomposed `grã`)

### Fixed

- gratia / et cetera not expanding when source used different Unicode form (NFC/NFD); rules now normalize before replace

## [0.3.0] - 2026-01-30

### Added

- High-end GPU detection (NVIDIA or AMD >= 8GB VRAM): triggers aggressive local training when on AC power (disabled on battery)
  - Local parallelism 12 (vs 6); Ollama num_ctx=8192; Layered Training default on
  - Auto-learn cap 4000 when GPU; Parallel spinbox to 16 when local
  - Env: EXPANDER_AGGRESSIVE_LOCAL (force on/off), EXPANDER_GPU_VRAM_MB (threshold)
- Automatic Gemini model detection from API with 24-hour caching (`expand_diplomatic/gemini_models.py`)
- GUI refresh button (⟳) to update available Gemini models from API
- Windows MSI installer build script (`scripts/build-windows-msi.sh`) using cx_Freeze
- Windows portable ZIP: flat structure (no subfolder when extracted); `build-windows-zip.sh`, `build-all.sh --zip`
- Pro model tests: timeout, retry, batch parallel cap (`tests/test_run_gemini.py`)
- Training examples expanded: 44 new Latin abbreviation pairs (62 total, was 18)
- **Expansion queue system**: Click Expand/Re-expand or navigate files while expansion is running to queue jobs
  - Expand button shows "Queued (N)" with queue count during expansion
  - Click Expand button again to toggle current file in/out of queue (no dialog)
  - Status bar shows "Queue: N" with queued count
  - "Clear Q" button to empty entire queue
  - Automatic sequential processing after current expansion completes
- **Double-click opens companion XML**: Double-clicking a line loads the companion file in the other panel and shows the matching line
  - Double-click in input → opens `filename_expanded.xml` in output (if it exists) and syncs to same block
  - Double-click in output → opens `filename.xml` in input (if it exists) and syncs to same block
  - Tracks `last_output_path` so output panel’s file is known; companion is always the correct paired file, not just the XML currently open

### Changed

- Speed: local rules pre-sort examples once per document (avoids per-block sort)
- Speed: GUI caches block ranges for click/double-click sync (avoids re-parsing)
- Speed: examples.json and learned_examples.json now mtime-cached to avoid redundant JSON parsing
- Gemini models now fetched from API at startup; hardcoded list serves as fallback
- Default Gemini model: `gemini-2.5-flash` (best value); model dropdown shows speed tick marks (······ = fastest)
- Build system: `build-all.sh` supports `--msi`, `--zip`; MSI also produces portable ZIP
- Whole-document expansion: `--block-by-block` default; Whole doc for batch; hang threshold 330s for whole-doc

### Fixed

- Invalid XML: guard when lxml returns None (e.g. "-", "{}"); clear error instead of crash
- Whole-doc progress: hang warning uses 330s threshold (not 90s) to avoid false positives
- Windows: prefs in `%APPDATA%`, cache in `%LOCALAPPDATA%`; Courier New font; setproctitle guarded
- Windows: paired-line highlight uses custom `paired` tag (sel invisible when unfocused)
- MSI: icon conversion PNG→ICO; `[ProgramFiles64Folder]`; `run_gemini` included; WSL2 uses `python.exe`

## [0.2.0] - 2026-01-30

### Added

- Collapsible image panel: upload any image format, display scaled to fit, resize on panel resize
- Layered Training checkbox: include `learned_examples.json` in the expansion prompt (curated + learned layers)
- Stream delay (ms) control: pace block-by-block output for visible real-time progress
- Double-click block selection: snap selection to full block and sync both panels
- File navigation: Prev (◀) and Next (▶) buttons; Ctrl+Left and Ctrl+Right shortcuts
- Autosave: save input to file when idle (toggle)
- Responsive layout: toolbar (grid), status bar (expandable progress), train section (expandable entries)
- Stretch Armstrong icon (window and dock)
- Pillow dependency for image handling
- Container: `build-container-installs.sh` for detected host (Apple Silicon → arm64, Intel → amd64)
- Learned examples cap increased to 2000 pairs
- GitHub repo creation and push

### Changed

- Hide Model dropdown when Backend is Local
- Remove deprecated `gemini-1.5-pro`; add `gemini-2.5-flash-lite`
- Gemini: use curated examples only by default; modality as `system_instruction`
- Re-expand: always use original file as source; incorporate learned pairs when Layered Training on
- README: Layered Training, image panel, Model visibility, Learn vs Layered Training
- Changelog: retroactive semver alignment

### Fixed

- Expansion quality: curated-only prompt for Gemini, modality as system instruction
- Pillow added to `requirements.txt` and `pyproject.toml` (required for GUI image features)

## [0.1.1] - 2026-01-29

### Added

- Cancel button and `ExpandCancelled`; expansion respects cancel request
- Auto-learn: extract pairs from successful Gemini expansions, save to `learned_examples.json`; GUI toggle
- `OLLAMA_TIMEOUT` environment variable for local backend
- `learned_examples.json` to `.gitignore`
- README rewritten for inexpert users (quick start, troubleshooting table)

### Changed

- Default Gemini model to `gemini-2.5-flash` (best price-performance)
- Container: `SKIP_OLLAMA_PULL` build arg, pip cache mount, improved `run-container.sh` env handling

### Fixed

- Build script typo: `multiarche` → `multiarch`
- Run ID check to prevent stale expansion results overwriting newer ones

## [0.1.0] - 2026-01-29

### Added

- Expand diplomatic transcriptions to full form via Gemini API or local (Ollama/rules-based fallback)
- TEI and PAGE XML support (`p`, `ab`, `l`, `seg`, `Unicode`, etc.)
- GUI: input/output panels, progress bar, model selection, modality selection
- CLI: `expand`, `train`, `test-gemini` subcommands
- Input→TXT and Output→TXT export
- Click block to select parallel block in other panel
- Docker container and multi-arch build support
- Examples from `examples.json`; add pairs via Train section or edit file directly
