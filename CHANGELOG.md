# Changelog

All notable changes to this project will be documented in this file.

The project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (semver).

## [Unreleased]

### Added

- High-end GPU detection (NVIDIA or AMD >= 8GB VRAM): triggers aggressive local training when on AC power (disabled on battery)
  - Local parallelism 12 (vs 6); Ollama num_ctx=8192; Layered Training default on
  - Auto-learn cap 4000 when GPU; Parallel spinbox to 16 when local
  - Env: EXPANDER_AGGRESSIVE_LOCAL (force on/off), EXPANDER_GPU_VRAM_MB (threshold)
- Automatic Gemini model detection from API with 24-hour caching (`expand_diplomatic/gemini_models.py`)
- GUI refresh button (⟳) to update available Gemini models from API
- Windows MSI installer build script (`scripts/build-windows-msi.sh`) using cx_Freeze
- Training examples expanded: 44 new Latin abbreviation pairs (62 total, was 18)
- **Expansion queue system**: Click Expand/Re-expand or navigate files while expansion is running to queue jobs
  - Expand button changes to "Queued" during expansion
  - Status bar shows "Queue: N" with queued count
  - "Clear Q" button to empty queue
  - Automatic sequential processing after current expansion completes
- **Smart file pairing on double-click**: Auto-loads correct paired file if input/output are mismatched
  - Double-click in input panel loads `*_expanded.xml` if available
  - Detects content mismatch (different file loaded) and auto-corrects
  - Status notification when paired file is loaded

### Changed

- Speed: local rules pre-sort examples once per document (avoids per-block sort)
- Speed: GUI caches block ranges for click/double-click sync (avoids re-parsing)
- Speed: examples.json and learned_examples.json now mtime-cached to avoid redundant JSON parsing
- Gemini models now fetched from API at startup; hardcoded list serves as fallback
- Build system: `build-all.sh` now supports `--msi` flag for Windows installer builds

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
