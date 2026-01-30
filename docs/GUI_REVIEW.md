# GUI Design Review

Review focused on **design intuitiveness** while preserving **simplicity**.

## Current strengths

- **Clear workflow**: Open → Expand → Save. Linear and obvious.
- **Side-by-side panels**: Input left, output right—standard diff/viewer pattern.
- **Primary actions prominent**: Open, Expand, Save in the main toolbar.
- **Recovery options**: API error dialog offers Enter key, Use local, Retry.
- **Progress feedback**: Status, progress bar, elapsed time, block N/M.
- **Click-to-sync**: Intuitive way to compare corresponding blocks.

## Intuitiveness improvements (minimal, keep simplicity)

1. **Keyboard shortcuts** — Add standard shortcuts so power users don’t need the mouse.
2. **Slightly clearer labels** — Small tweaks for "Passes" and optional grouping.
3. **Visual grouping** — Light separation between primary actions and settings.

## Recommendations applied

- **Keyboard shortcuts**: Ctrl+O (Open), Ctrl+S (Save), Ctrl+E (Expand).
- **Passes label**: "Passes (1–5):" to clarify valid range.
- **Visual grouping**: Thin vertical separator between primary actions and settings.
- **Comments**: Toolbar code annotated for primary actions vs settings.
- Overall layout and design unchanged.
