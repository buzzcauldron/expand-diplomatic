# Release readiness review

Review date: 2025-02 (pre-release). This checklist and notes support cutting a release (e.g. 0.3.4) from current `main`.

---

## ✅ Tests and lint

- **Tests**: All 24 tests pass (`pytest tests/`). Covers expander (rules, local, dry-run, invalid XML), run_gemini (timeout, retry, pro model, batch parallel).
- **Lint**: No linter errors reported on `gui.py`, `expander.py`, `learning.py`, or other edited files.
- **Print usage**: All `print()` in the codebase are intentional (CLI output / stderr). No stray debug prints.

---

## ✅ Version and docs

- **Version**: `pyproject.toml` and `expand_diplomatic/_version.py` both have `0.3.3`. For a new release, bump to `0.3.4` (or next) and move **[Unreleased]** in CHANGELOG into **## [0.3.4] - YYYY-MM-DD**.
- **CHANGELOG**: [Unreleased] is filled with recent features and changes; a few late items (`.env` path, focus during expand, parallel scroll, resizable dialogs, paned sash) were added in this review.
- **README**: Covers quick start, GUI (actions, settings, Review learned, status bar, Max ex/Strategy), CLI (expand, train, eval, --backend rules, --max-examples), teaching (project vs personal learned), Docker, Windows (ZIP/MSI), builds, troubleshooting.
- **LICENSE**: Present (MIT). `.gitignore` excludes `.env` and build artifacts.

---

## ✅ Security and secrets

- No API keys or secrets in code. Keys come from environment, `.env` (user-writable path when installed), or dialog.
- `.env` is in `.gitignore`. Save-to-.env uses a writable path (project root when run from source, config dir when installed).

---

## ✅ Dependencies

- **pyproject.toml**: `google-genai`, `lxml`, `python-dotenv`, `Pillow` with version bounds. Optional `setproctitle` (dock).
- **requirements.txt**: Same plus `google-auth` (likely transitive of google-genai; not in pyproject but often used for local installs). Consider aligning if you want a single source of truth.

---

## ✅ Build and packaging

- Scripts present: `build-all.sh`, `build-packages.sh`, `build-deb.sh`, `build-rpm.sh`, `build-macos-app.sh`, `build-docker.sh`, `build-windows-msi.sh`, `build-windows-zip.sh`, and Windows `.bat` wrappers.
- Entry points: `expand-diplomatic` (CLI), `expand-diplomatic-gui` (GUI). `run_gemini` and `gui` listed as py-modules where needed.

---

## ✅ GUI and UX

- Main window: resizable, minsize, status bar (visible on first Expand), paned sash for resizing middle/bottom.
- Dialogs: Diff, Edit pair, Yes/No, API key, error — all resizable with minsize.
- Review learned: staging filter, keep selection on Accept/Reject, scroll, editable list, autosave.
- Focus: Synced block stays in view during expansion; single/double-click align blocks in parallel (_scroll_line_to_top).

---

## ⚠️ Optional before release

1. **Bump version**: Set `0.3.4` (or next) in `_version.py` and `pyproject.toml`; add `## [0.3.4] - YYYY-MM-DD` in CHANGELOG and move Unreleased content there.
2. **requirements vs pyproject**: Decide whether `requirements.txt` should be generated from pyproject or kept in sync by hand; `google-auth` is only in requirements today.
3. **Deprecation warning**: pytest run shows one deprecation from `google.genai.types` (Python 3.17). No action required for current release; track for future dependency upgrade.

---

## Summary

The project is **release-ready** from a code, test, and documentation standpoint. Remaining steps are to bump the version, finalize CHANGELOG for the new version, and run your usual build/package and smoke-test steps before tagging and publishing.
