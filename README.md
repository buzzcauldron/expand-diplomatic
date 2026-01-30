# Diplomatic Transcription Expander

Expand diplomatic transcriptions to full form using the Gemini API. Input: TEI-like XML (or raw XML). Output: same XML with **only text inside elements** changed; structure is preserved.

- **Input**: local file path(s) or raw XML string  
- **Output**: XML to XML  
- **Examples**: configurable via `examples.json` (single pair now; add more over time)  
- **Model**: Gemini (default `gemini-2.5-pro`; use `gemini-3-pro-preview` if you have access)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

Set your API key (either method):

```bash
export GEMINI_API_KEY="your-api-key"
```

**Store but don't commit:** Copy `.env.example` to `.env`, add your key, and use it locally. `.env` is gitignored — keep it active locally only; **never commit or push `.env` to GitHub**.

Optional: `GEMINI_MODEL` (default `gemini-2.5-pro`), `EXPANDER_EXAMPLES` (path to examples JSON).

## Examples file

Edit `examples.json` (or the path you pass via `--examples`):

```json
[
  { "diplomatic": "y^e same", "full": "the same" },
  { "diplomatic": "another abbrev.", "full": "another abbreviation" }
]
```

Add as many pairs as you like; they are used as few-shot examples in the prompt. You can also **train locally** with the `train` subcommand (no API key required):

```bash
python -m expand_diplomatic train                    # interactive: add pairs one by one
python -m expand_diplomatic train --list             # list current pairs
python -m expand_diplomatic train --add -d "⁊c̃" -f "et cetera"   # add one pair
python -m expand_diplomatic train --examples my.json --add -d "..." -f "..."
```

All data stays local (`examples.json` or `--examples` path). These examples are used only when building prompts for the expander.

## GUI

A minimal Tkinter GUI (side‑by‑side input/output, Load / Expand / Save, train panel) is provided:

```bash
python gui.py
```

Requires `tkinter` (usually bundled with Python). Set `GEMINI_API_KEY` or use `.env` before expanding. **Backend** (Gemini API / local Ollama) and **Modality** (full, conservative, normalize, aggressive) are aligned: choose both before Expand. Expansion is Latin-only; the model is instructed not to translate into English or other languages.

**API errors:** If expand fails (no key, 429, etc.), the GUI offers: **Enter API key** (paste key, optionally save to `.env`), **Use local model**, or **Use online Gemini**. You can also retry with the same setup. **Local model** tries Ollama first; if Ollama isn’t running, it falls back to **rule-based expansion** using your Train examples (no server). Retry always **reloads examples from disk** (retrain) so new pairs are used.

**Startup:** The GUI and CLI use lazy imports so startup stays fast. The GUI loads only `examples_io` (no Gemini/lxml) until you click Expand; `train` never loads the expander.

## Command-line (CLI)

Run via module or console script (after `pip install -e .`):

```bash
python -m expand_diplomatic [expand] --file document.xml
expand-diplomatic --file document.xml
```

Subcommands:

- **expand** (default) — expand XML using Gemini or local Ollama  
- **train** — add/list example pairs (see Examples file)

## Usage

**Text (raw XML string):**

```bash
python -m expand_diplomatic --text "<TEI>...</TEI>"
```

**Single file:**

```bash
python -m expand_diplomatic --file path/to/document.xml
```

**Batch (multiple files):**

```bash
python -m expand_diplomatic --batch a.xml b.xml c.xml
```

**Batch directory:**

```bash
python -m expand_diplomatic --batch-dir ./input_xml
```

**Local model** (Ollama if available, else rule-based from examples; no API key):

```bash
python -m expand_diplomatic --backend local --file document.xml
python -m expand_diplomatic --backend local --local-model llama3.1 --batch-dir ./xml
```

**API key:** use `GEMINI_API_KEY` / `GOOGLE_API_KEY` or `.env`, or `--api-key KEY`, or `--prompt-key` to be prompted interactively when missing.

**Output:**

- Single file: writes `*_expanded.xml` next to the input unless `--out` is given.  
- Batch: uses `--out-dir` if set; otherwise writes `*_expanded.xml` next to each input.  
- `--text`: prints expanded XML to stdout unless `--out` is used.

**Options:**

- `--examples PATH` — path to `examples.json` (default: `./examples.json`)  
- `--model ID` — Gemini model (default: `GEMINI_MODEL` or `gemini-2.5-pro`)  
- `--backend {gemini,local}` — Gemini API or local (Ollama → rules fallback)  
- `--local-model ID` — Ollama model when `--backend local` (default: `llama3.2`). If Ollama is down, rules from examples are used.  
- `--modality {full,conservative,normalize,aggressive}` — expansion style (default: `full`). **Conservative**: abbreviations/superscripts only; **normalize**: spacing, punctuation, common abbreviations; **aggressive**: full modern prose. Output is Latin-only (no translation to English or other languages).  
- `--api-key KEY` — Gemini API key (overrides env)  
- `--prompt-key` — prompt for API key on stdin when missing  
- `--out PATH` — output path (single file or `--text`)  
- `--out-dir PATH` — output directory for batch runs  
- `--files-api` — upload input file(s) via the [Gemini Files API](https://ai.google.dev/api/files) and pass them as context (`--file` / `--batch` only)  
- `--dry-run` — skip LLM; leave block text unchanged

## Files API

With `--files-api`, input files are uploaded via the [Gemini Files API](https://ai.google.dev/api/files) and attached to each Gemini request as context. Gemini can use the full document when expanding each block. Use with `--file` or `--batch`:

```bash
python -m expand_diplomatic --file document.xml --files-api
python -m expand_diplomatic --batch-dir ./xml --out-dir ./expanded --files-api
```

Standalone `run_gemini.py` also supports file upload:

```bash
python run_gemini.py --prompt "Summarize this." --file document.pdf
```

## Container (Docker)

Use `run-container.sh` on **Mac**, **Linux**, or **Windows (WSL2)** to run `expand_diplomatic` in Docker. Paths are relative to the workspace (default: current directory), which is mounted at `/workspace`. Images support **linux/amd64** (x64) and **linux/arm64** (Mac Silicon, ARM). Optional: **linux/arm/v7** (32-bit ARM) via `--platform`; may need build deps in image.

The image includes **Ollama** and a baked-in model (**llama3.2** by default). Use `--backend local` to expand with the local model and no API key; the container starts Ollama automatically.

```bash
export GEMINI_API_KEY="your-api-key"
./run-container.sh --build -- --file sample.xml --out sample_expanded.xml

# Local model only (no API key):
./run-container.sh --build -- --backend local --file sample.xml --out sample_expanded.xml
```

**Options:**

- `--workspace DIR` — directory to mount at `/workspace` (default: `$(pwd)`).
- `--build` — build the image before running (run once after clone or when Dockerfile changes).
- `--platform PLAT` — use image for `linux/amd64` or `linux/arm64` (default: host).
- `--` — everything after is passed to `expand_diplomatic`.

**Keep the local Ollama model updated:** set `OLLAMA_UPDATE_MODEL=1` (and optionally `OLLAMA_MODEL`, default `llama3.2`) before running. The container will `ollama pull` that model on each start so you stay on the latest version without rebuilding.

```bash
OLLAMA_UPDATE_MODEL=1 ./run-container.sh -- --backend local --file sample.xml --out sample_expanded.xml
```

**Examples:**

```bash
./run-container.sh --build -- --file sample.xml --out sample_expanded.xml
./run-container.sh --build -- --backend local --file sample.xml --out sample_expanded.xml
./run-container.sh --workspace /path/to/xml -- --batch-dir . --out-dir ./expanded
```

Requires [Docker](https://docs.docker.com/get-docker/) and a running daemon.

## Packaging (x64 & Mac Silicon)

**Wheels and sdist** (universal `py3-none-any`; works on x64 and Mac Silicon):

```bash
pip install build wheel   # or: pip install -e ".[dev]"
./scripts/build-packages.sh
```

Output: `dist/` with `*.tar.gz` and `*.whl`. Install with `pip install dist/*.whl`.

**Docker multi-arch** (linux/amd64, linux/arm64 — Mac, Linux, Windows via WSL2). The image installs **Ollama** and pulls **llama3.2** at build time; override with build args `OLLAMA_MODEL` or `OLLAMA_VERSION`:

```bash
./scripts/build-docker.sh          # build all platforms (includes Ollama + llama3.2)
./scripts/build-docker.sh --load   # build native arch and load into Docker
./scripts/build-docker.sh --push   # build and push to registry (set IMAGE_NAME)
./scripts/build-docker.sh --platform linux/amd64,linux/arm64,linux/arm/v7  # add arm/v7 (may need build deps)

docker build --build-arg OLLAMA_MODEL=llama3.2:1b -t expand-diplomatic .   # smaller/faster build
```

On **Windows**, use [Docker Desktop](https://docs.docker.com/desktop/install/windows-install/) with WSL2 and run `run-container.sh` from WSL or a Git Bash–style shell.

**CI:** `.github/workflows/build.yml` builds wheels on `ubuntu-latest` and `macos-latest`, and Docker multi-arch `linux/amd64,linux/arm64` (no push). Docker build installs Ollama and pulls the default model, so it can take several minutes. Artifacts: `dist-ubuntu` and `dist-macos`.

## Sample

`sample.xml` is a minimal TEI example. Replace the placeholder entries in `examples.json` with your own diplomatic → full pairs, then run for example:

```bash
python -m expand_diplomatic --file sample.xml --out sample_expanded.xml
```

## Gemini integration

Gemini is called via `run_gemini.py`, which supports the [Files API](https://ai.google.dev/api/files) for file uploads. Standalone:

```bash
python run_gemini.py --prompt "Your prompt" [--model gemini-2.5-pro] [--temperature 0.2] [--file path/to/file]
```

**Credit.** The `run_gemini.py` script follows the pattern from [ideasrule/latin_documents](https://github.com/ideasrule/latin_documents) (`google.genai` client, `GenerateContentConfig`).

## Notes

- Target elements: TEI-style blocks `p`, `ab`, `l`, `seg`, `item`, `td`, `th`, `head`, `figDesc`, plus PAGE `Unicode` (e.g. eScriptorium output). Configurable in code if needed.  
- Only **text inside** those elements is modified; attributes and structure are kept.  
- Nested blocks (e.g. `p` inside `div`) are handled so that only innermost blocks are expanded; parent structure is preserved.  
- Provide at least one example pair in `examples.json` before running.  
- To use **Gemini 2.5 Pro** or **Gemini 3 Pro** (if available), set `GEMINI_MODEL=gemini-2.5-pro` or `gemini-3-pro-preview`.
- **Versioning:** [Semantic Versioning](https://semver.org/) (semver). Project version in `pyproject.toml` and `expand_diplomatic.__version__`; dependencies use compatible ranges (`>=X.Y.Z,<X+1`). `expand_diplomatic --version` prints the current version.
- **Design:** See [docs/DESIGN.md](docs/DESIGN.md) for the **visual page editor** reference model (Transkribus, eScriptorium, PAGE Viewer, Scribe) and **language choice** (Python core; TypeScript/web or Python+Qt for the editor).
- **Model capabilities:** See [docs/MODEL_CAPABILITIES.md](docs/MODEL_CAPABILITIES.md) for a **demo** (input → rules vs Ollama vs Gemini) and what each backend can do.
