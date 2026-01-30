# Design: reference model and language choice

## Visual page editor as reference model

The tool should align with **visual page editors** used in document transcription and OCR proofreading:

| Tool | Description |
|------|-------------|
| **Transkribus** | Browser-based; side‑by‑side **document image + text editor**; centers on current line; virtual keyboard, collaboration. |
| **eScriptorium** | Web app; PAGE/ALTO; **Transcription** (layout) and **Text** (linear) panels; import/export, Kraken models. |
| **PAGE Viewer** (PRImA) | Desktop (Java); **layout overlay on document image**; PAGE/ALTO; tooltips for text and attributes. |
| **Scribe OCR** | Web (JavaScript); **editable text overlay** on source images; proofreading / OCR / ebook modes; custom overlay fonts. |

Common traits: **image + overlaid or adjacent editable text**, **line/region‑aware editing**, support for **PAGE** (and often ALTO), **zoom/pan**, and optionally **virtual keyboards** and **collaboration**.

For *expand diplomatic*, the target UX is:

- Show the **page image** (from `Page` / `imageFilename` in PAGE).
- Overlay **TextLine** regions (from `Coords` / `Baseline`) and link each to its **Unicode** (diplomatic) and expanded text.
- Let the user **select a line** → edit or **expand** its text → persist back into PAGE XML.
- Optional: side‑by‑side **diplomatic vs full** view, train panel, batch expand.

The current **Tkinter GUI** is a minimal step (input/output panes, no image, no overlay). Moving toward the reference model means adding **image + overlay** and **line‑level** interaction.

---

## Language choice

### Core (expansion, train, batch, API)

**Python** is a good fit and already used:

- **XML** (lxml), **Gemini** (google‑genai), **examples** (JSON), **.env** (python‑dotenv).
- **CLI** (argparse), **batch** scripts, **container** (Docker) all straightforward.
- Strong ecosystem for NLP/document processing and rapid iteration.

Recommendation: **keep the core in Python** (expander, `run_gemini`, train, CLI, batch).

### Visual page editor frontend

Reference tools (Transkribus, eScriptorium, Scribe) are **web‑based**; PAGE Viewer is **Java** desktop. Two realistic paths:

#### 1. **TypeScript / JavaScript (web)**

- **Pros:** Matches Transkribus, eScriptorium, Scribe; **canvas/SVG** for image + overlay, zoom, pan; runs everywhere; no install; easier virtual keyboards, sharing, future collab.
- **Cons:** Separate frontend codebase; Python backend (e.g. small HTTP API) for expand/train, or CLI called from Electron.

**Best if:** You want a **browser app** or **Electron** desktop app, maximum reach, and a UI that mirrors modern transcription tools.

#### 2. **Python + Qt (PyQt / PySide)**

- **Pros:** **Single language**; **QGraphicsView** (or similar) for image, overlays, zoom, pan; line‑level selection and editing; desktop‑only but no browser.
- **Cons:** Heavier than Tkinter; packaging/distribution more involved than “open in browser.”

**Best if:** You prefer **one stack**, **desktop‑only**, and are okay with Qt’s dependency and learning curve.

### Summary

| Layer | Suggested language | Rationale |
|-------|--------------------|-----------|
| **Core** (expand, train, batch, Gemini, XML) | **Python** | Existing codebase; libraries; CLI/batch/container. |
| **Visual page editor** | **TypeScript (web)** or **Python + Qt** | Web: alignment with reference tools, overlay/UX, reach. Qt: single language, capable desktop editor. |

The **best language for the overall tool** is **Python for the backend** either way. The main choice is **frontend**: **TypeScript (web)** for a reference‑style visual page editor, or **Python + Qt** for an all‑Python desktop editor.
