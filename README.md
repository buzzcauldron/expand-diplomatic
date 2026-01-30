# Diplomatic Transcription Expander

Turn abbreviated medieval Latin text (diplomatic transcriptions) into full, readable form. You give it an XML file with the original text; it gives back the same file with abbreviations expanded.

**You need:** Python 3.10+ and (for online expansion) a free Gemini API key.

---

## Quick start (easiest way)

1. **Install Python**  
   If you don’t have it, download from [python.org](https://www.python.org/downloads/). On install, check “Add Python to PATH.”

2. **Get an API key** (free)  
   Go to [Google AI Studio](https://aistudio.google.com/apikey) and create an API key. You’ll paste it into the app.

3. **Open the app**  
   In a terminal/command prompt, go to the project folder and run:
   ```bash
   python gui.py
   ```

4. **Use it**  
   - Click **Open…** and choose your XML file  
   - Paste your API key when asked (or put it in a `.env` file once)  
   - Click **Expand**  
   - Click **Save…** when done

---

## Step-by-step setup

### 1. Install dependencies

Open a terminal (or Command Prompt on Windows) in the project folder and run:

```bash
python -m venv .venv
```

On **Mac/Linux:**
```bash
source .venv/bin/activate
```

On **Windows:**
```bash
.venv\Scripts\activate
```

Then:
```bash
pip install -r requirements.txt
```

*(These commands create an isolated environment and install the required libraries.)*

### 2. Set your API key

You have two options:

**Option A – Paste when asked**  
The app will ask for your key the first time you expand. You can choose to save it in a `.env` file so you don’t have to enter it again.

**Option B – Save it beforehand**  
Copy `.env.example` to `.env` in the project folder, open `.env` in a text editor, and add:
```
GEMINI_API_KEY=your-api-key-here
```
Get a key at [Google AI Studio](https://aistudio.google.com/apikey).

**Important:** Never share or upload `.env` — it contains your secret key.

---

## Using the graphical interface (GUI)

Run:
```bash
python gui.py
```

### Main actions

| Button | What it does |
|--------|--------------|
| **Open…** | Load an XML file |
| **Expand** | Expand abbreviations (online with Gemini or locally) |
| **Save…** | Save the expanded result |
| **◀** / **▶** | Previous/next XML file in the same folder |
| **Re-expand** | Re-expand from the original file; keeps original on left, new result on right. Uses updated examples and learned pairs. |

**Keyboard shortcuts:** Ctrl+O (Open), Ctrl+S (Save), Ctrl+E (Expand), Ctrl+← / Ctrl+→ (prev/next file in folder)

### Settings

- **Backend** – Use **Gemini** (online, needs API key) or **Local** (no key, uses rules or Ollama).
- **Model** – Which Gemini model to use (hidden when Backend is Local). Default is a good balance of speed and cost.
- **Modality** – Expansion style: full, conservative, normalize, aggressive, or **local** (tuned for non-Gemini models like Ollama; not the default).
- **Parallel** – How many blocks to process at once. Lower this (e.g. 1) if you see rate limit errors.
- **Learn** – When on, the app saves new abbreviation pairs from each expansion to improve future runs.
- **Layered Training** – When on, includes learned examples in the expansion prompt (curated + learned).

### If expansion fails

- **No API key** – Paste your key when prompted, or add it to `.env`.
- **Rate limit (429)** – Lower **Parallel** to 1, wait a minute, then try again.
- **Timeout / hangs** – Try the **Local** backend, or add `GEMINI_TIMEOUT=60` to `.env`.
- **Want to avoid the API** – Switch **Backend** to **Local**; the app will use rules and (if installed) Ollama.

### Extra features

- **Input→TXT** / **Output→TXT** – Export text blocks to plain `.txt` files.
- **Click to sync** – Click a block in input or output to jump to the matching block in the other panel. Double-click to select the full block.
- **Image panel** – Click the 🖼▶ strip on the right to expand and upload an image for reference.
- **Passes** – Run expansion more than once in a row to refine the text.

---

## Teaching the app (examples)

The app learns from example pairs: “this abbreviation” → “this full form”.

### In the GUI

Use the **Train** section at the bottom:

1. Type the abbreviated form in **Diplomatic** (or click **From input** to copy from a block).
2. Type the full form in **Full** (or click **From output**).
3. Click **Add pair**.

### Or edit the examples file

Open `examples.json` in a text editor. Add pairs like this:

```json
[
  { "diplomatic": "grã", "full": "gratia" },
  { "diplomatic": "tempꝰ", "full": "tempus" }
]
```

More examples = better results. The app also saves learned pairs from expansions when **Learn** is on. Use **Layered Training** to include those learned pairs in the prompt.

---

## Command-line usage

For single files:
```bash
python -m expand_diplomatic --file document.xml
```

Output is saved as `document_expanded.xml` next to the original.

For many files:
```bash
python -m expand_diplomatic --batch-dir ./my_xml_folder --out-dir ./expanded
```

Use the local backend (no API key):
```bash
python -m expand_diplomatic --backend local --file document.xml
```

---

## File types and format

- **Input:** XML files (e.g. TEI, PAGE XML).
- **Output:** Same structure, with only the text inside elements changed.
- **Blocks:** Paragraphs, lines, and similar elements (e.g. `p`, `l`, `Unicode` in PAGE) are expanded. Structure and attributes stay the same.

---

## Advanced options

- **Container (Docker):** See the Container section below if you prefer to run in Docker.
- **Modality:** `full` (default), `conservative`, `normalize`, `aggressive` — control how much the text is modernized.
- **Environment variables:**  
  `GEMINI_MODEL`, `GEMINI_TIMEOUT`, `EXPANDER_MAX_CONCURRENT` and others can be set in `.env` or your system environment. See `.env.example` for details.

---

## Container (Docker)

If you use Docker, you can run the app in a container. Builds default to your detected hardware (Apple Silicon → arm64, Intel/AMD → amd64).

```bash
export GEMINI_API_KEY="your-api-key"
./run-container.sh --build -- --file sample.xml --out sample_expanded.xml
```

For local expansion only (no API key):
```bash
./run-container.sh --build -- --backend local --file sample.xml --out sample_expanded.xml
```

**Build options:**
- `./scripts/build-container-installs.sh` — Build for detected host (native arch)
- `./scripts/build-container-installs.sh --all` — Build linux/amd64 and linux/arm64
- `./scripts/build-docker.sh --load` — Same (native only); `--skip-ollama` for faster build

On Apple Silicon, uses arm64 (native) by default, not amd64 (emulated).

You need [Docker](https://docs.docker.com/get-docker/) installed and running.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| “No module named …” | Run `pip install -r requirements.txt` (with your venv activated). |
| “API key” error | Add your key to `.env` or paste it when the app asks. |
| 429 / rate limit | Lower **Parallel** to 1 and wait before retrying. |
| Slow or stuck | Use **Local** backend or set `GEMINI_TIMEOUT=60` in `.env`. |
| “Ollama not reachable” | Either start Ollama (`ollama serve`) or ignore it — the app falls back to rule-based expansion. |
| Wrong expansions | Add more example pairs in Train or `examples.json`. |

---

## More options (CLI)

Useful flags when running from the command line:

- `--examples PATH` — Use a different examples file
- `--model ID` — Change Gemini model (e.g. `gemini-2.5-pro`)
- `--modality {full,conservative,normalize,aggressive,local}` — Expansion style (`local` is tuned for non-Gemini models)
- `--passes N` — Run expansion multiple times (1–5)
- `--files-api` — Upload the full file to Gemini for extra context

See `.env.example` for environment variables (timeouts, retries, etc.).

---

## Credits

The Gemini integration follows the approach from [ideasrule/latin_documents](https://github.com/ideasrule/latin_documents).
