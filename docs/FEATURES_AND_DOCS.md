# Features and documentation status

This note summarizes what is implemented and documented vs what was missing or is planned.

---

## Recently documented (were missing from README/CHANGELOG)

The following are **implemented** but were under-documented; they are now in the README and/or CHANGELOG:

| Area | What was missing | Where it’s documented now |
|------|------------------|---------------------------|
| **Review learned** | Staged pairs, Accept/Reject/Promote, personal vs project | README: “Review learned (staged pairs)”, “Teaching the app” (where learned pairs live), Settings (Learn, Max ex, Strategy) |
| **CLI eval** | `python -m expand_diplomatic eval` | README: “Command-line usage”, “More options (CLI)” |
| **CLI train** | `train` subcommand | README: “More options (CLI)” |
| **Backend rules** | `--backend rules` (examples only, no API/Ollama) | README: “Command-line usage”, “More options (CLI)” |
| **Prompt budget** | Max ex, Strategy (GUI); `--max-examples`, `--example-strategy` (CLI) | README: Settings, Extra features, “More options (CLI)” |
| **Personal vs project learned** | Two tiers, Promote vs Accept, config path | README: “Teaching the app”, “Review learned” |
| **Status bar** | Visible on first Expand, then stays | README: Extra features |
| **Recent GUI/behavior** | Status bar, scroll, review keep position, rules filter, toolbar spacing | CHANGELOG: [Unreleased] |

---

## Implemented and already documented

- Quick start, step-by-step setup, API key, GUI main actions and shortcuts
- Expansion queue (Queued (N), Clear Q)
- Backend (Gemini / Local), Model, Whole doc, Modality, Parallel, Learn, Layered Training
- Diff, Input→TXT, Output→TXT, click/double-click sync, image panel, Passes, preferences
- Teaching (Train, examples.json, learned), workflow, CLI usage (--file, --batch-dir, --backend local)
- File types, pairing, batch skip _expanded, format detection
- Docker, Windows (ZIP/MSI), build scripts, troubleshooting, env vars

---

## Not implemented (design / future)

From [DESIGN.md](DESIGN.md), the **reference model** is a visual page editor with:

- **Page image** from PAGE XML (e.g. `imageFilename`) shown in the UI
- **Overlay** of text lines (e.g. TextLine regions from Coords/Baseline) on the image
- **Line-level** selection and editing linked to Unicode (diplomatic) and expanded text
- Optional: zoom/pan, virtual keyboards, collaboration

The **current GUI** is a minimal step: input/output text panes, image strip (reference image only, not PAGE-linked overlay), Train, Batch, Review learned. Moving toward the reference model would mean adding **image + overlay** and **line-level** interaction (e.g. TypeScript/web or Python + Qt as in DESIGN.md).

---

## Summary

- **Missing material** (docs): Addressed by updating README and CHANGELOG for Review learned, eval/train, backend rules, prompt budget, personal vs project learned, status bar, and recent GUI changes.
- **Missing features** (code): The only “missing” features relative to the design doc are the **visual page editor** pieces (image from PAGE + overlay + line-level editing), which are listed there as a future direction, not as current scope.
