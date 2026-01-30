# What the model is capable of

This demo uses **`demo_latin.xml`**: three short Latin paragraphs with diplomatic abbreviations (e.g. `eccl̃ia`, `ꝑ`, `grã`) from `examples.json`.

---

## Input (`demo_latin.xml`)

```xml
<p>dño nr̃e Eboraceñ eccl̃ia grã ꝑpetuo.</p>
<p>p̾benda ꝑ capitl̃i tempꝰ lib̃alit̾ concessa.</p>
<p>⁊c̃ ꝑ Dunolm̃ Wichtoñ.</p>
```

---

## 1. Rules-based (local, no Ollama)

**Backend:** `local` with **rules fallback** (no LLM).  
**What it does:** Replaces each diplomatic form with its **full** form using your **examples** only. Longest match first. No API, no Ollama.

**Output:**

```xml
<p>domino nostre Eboracensis ecclesia gratia perpetuo.</p>
<p>prebenda per capituli tempus liberaliter concessa.</p>
<p>et cetera per Dunelm Wighton.</p>
```

| Diplomatic | Full        |
|------------|-------------|
| `dño`      | domino      |
| `nr̃e`      | nostre      |
| `Eboraceñ` | Eboracensis |
| `eccl̃ia`   | ecclesia    |
| `grã`      | gratia      |
| `ꝑpetuo`   | perpetuo    |
| `p̾benda`   | prebenda    |
| `ꝑ`        | per         |
| `capitl̃i`  | capituli    |
| `tempꝰ`    | tempus      |
| `lib̃alit̾`  | liberaliter |
| `⁊c̃`       | et cetera   |
| `Dunolm̃`   | Dunelm      |
| `Wichtoñ`  | Wighton     |

Deterministic, Latin-only, no translation. Add more pairs in **Train** or `examples.json` to expand more forms.

---

## 2. Ollama (local LLM)

**Backend:** `local` with **Ollama** (e.g. `llama3.2` in Docker).  
**What it does:** Uses the same **modality** prompts (full / conservative / normalize / aggressive) and **examples** as few-shot. Instructed to **keep the full form in Latin** and **not translate to English**. Can generalize beyond exact example strings.

**Capable of:**

- Expanding abbreviations and superscripts even when not literally in examples.
- Normalizing spacing and punctuation.
- Producing fluent Latin when using **conservative** or **normalize**; **aggressive** can modernize more.

**Caveat:** The LLM sometimes echoes prompt structure (e.g. `Diplomatic:` / `Full:`) into the output. Use **conservative** or **normalize** to reduce this; we’re improving prompts to strip or avoid leakage.

---

## 3. Gemini (API)

**Backend:** `gemini` (Gemini API).  
**What it does:** Same modality + examples + **Latin-only, no English** instruction. Often gives the strongest expansion quality and fewer formatting artifacts. Requires `GEMINI_API_KEY`.

---

## Try it yourself

```bash
# Rules only (fast, no Ollama)
python -m expand_diplomatic --backend local --modality full --file demo_latin.xml --out out_rules.xml

# Ollama (container)
./run-container.sh -- --backend local --modality conservative --file demo_latin.xml --out out_ollama.xml

# Gemini (optional)
python -m expand_diplomatic --backend gemini --modality full --file demo_latin.xml --out out_gemini.xml
```

Use **Backend** and **Modality** in the GUI the same way.
