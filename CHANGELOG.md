# Changelog

All notable changes to this project will be documented in this file.

The project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (semver).

## [Unreleased]

### Changed

- Speed: local rules pre-sort examples once per document (avoids per-block sort)
- Speed: GUI caches block ranges for click/double-click sync (avoids re-parsing)

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
