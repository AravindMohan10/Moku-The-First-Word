---
title: Moku The First Word
emoji: 🌲
colorFrom: green
colorTo: yellow
sdk: gradio
sdk_version: 5.0.0
app_file: app.py
pinned: false
license: apache-2.0
---

# Moku: The First Word

A tiny forest society where small LLM-driven creatures invent glyphs, remember what happened, build trust, and learn that words can mean food, danger, shelter, and eventually lies.

## What It Is

Moku is a whimsical live simulation built for a fast hackathon demo. The Python engine owns the world rules: movement, hunger, fear, food, hazards, visibility, scoring, validation, traces, and rendering. The model owns the creature minds: glyph choice, interpretation, memory use, trust updates, social behavior, deception, and action selection.

The UI is designed as a forest observatory, not a dashboard. You mostly watch the world. Explanations, traces, dictionary guesses, trust, creature cards, and deception notes live in the slide-out details panel.

## Modes

- **Sandbox**: seeded, demo-safe, and paced for a visible story arc. Events arrive on schedule so a judge can see language, scarcity, strangers, danger, and drift quickly.
- **Wild run**: less guided and slower. The map, social life, and glyph meanings diverge with fewer rails.

Both modes use the same creature policy path.

## Current Features

- Immersive Gradio simulation with custom CSS and animated forest scene.
- Two watch modes: `Sandbox` and `Wild run`.
- Six to ten tiny creatures with distinct generated SVG looks.
- Food, danger, shelter, rain, scarcity, stranger events, and ambient forest motion.
- Public glyph speech bubbles with invented words only.
- Slide-out field observatory for transcript, language evolution, glyph drift, social graph, field notes, dictionary, mind traces, trust, deception, and creature roster.
- Per-creature memory through Mem0 when configured, with reliable SQLite keyword fallback.
- Strict `CreatureTurn` schema, lenient JSON extraction/repair, target fixing, memory sanitization, and action post-processing.
- LLM routing through Hugging Face Inference Providers or a local OpenAI-compatible endpoint.
- Turn-by-turn mind traces with latency, provider, retrieved memory count, intended meaning, interpretation, and fallback status.
- JSON trace export and trace-to-SFT conversion.
- Modal/vLLM helper for local-style serving and LoRA training experiments.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Then open `http://localhost:7860`.

If no model provider is configured, creature minds fall back through the deterministic policy path while preserving traceability.

## Model And Memory Configuration

**OpenBMB (hackathon primary):** `openbmb/MiniCPM3-4B` — no exact 3B checkpoint; this 4B model still qualifies for Tiny Titan (≤4B) and targets OpenBMB Awards. It is not available on HF Inference Providers for most accounts; serve it via Modal vLLM or a local OpenAI-compatible server.

Hugging Face provider (dev fallback when Modal is offline):

```bash
HF_TOKEN=...
MOKU_LLM_PROVIDER=auto
MOKU_HF_MODEL=openbmb/MiniCPM3-4B
MOKU_HF_MODEL_FALLBACKS=Qwen/Qwen2.5-Coder-3B-Instruct,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B
```

Modal vLLM (recommended judge demo — see `modal/moku_modal.py`):

```bash
MOKU_LLM_PROVIDER=auto
MOKU_MODEL_BASE_URL=https://<workspace>--moku-the-first-word-serve.modal.run/v1
MOKU_HF_MODEL=openbmb/MiniCPM3-4B
MOKU_MODEL_API_KEY=local
```

Local llama.cpp / other OpenAI-compatible server:

```bash
MOKU_LLM_PROVIDER=local
MOKU_MODEL_BASE_URL=http://127.0.0.1:8080/v1
MOKU_HF_MODEL=openbmb/MiniCPM3-4B
MOKU_MODEL_API_KEY=local
```

Mem0:

```bash
MEM0_API_KEY=...
```

Each creature uses a namespace shaped like:

```text
world:{world_id}:creature:{creature_id}
```

If Mem0 is unavailable, the app mirrors and searches memories with local SQLite at `data/moku_memories.sqlite3`.

## Repo Layout

- `app.py` - Gradio app, navigation, timers, controls, and trace export.
- `moku/sim_engine.py` - world state, turn loop, creature policy orchestration, glyph evolution, deception, chronicles, and reports.
- `moku/render_world.py` - immersive forest renderer, creature SVGs, guide, side panel, and scene shell.
- `moku/memory.py` - Mem0 plus SQLite fallback memory abstraction.
- `moku/llm_client.py` - Hugging Face/local LLM routing and chronicle/epilogue calls.
- `moku/json_repair.py` - lenient model JSON parsing and repair.
- `moku/turn_postprocess.py` - target, memory, and action cleanup before execution.
- `moku/visual_layers.py` - overlay toggle model.
- `moku/web/` - CSS and small browser-side panel scripts.
- `scripts/generate_dataset.py` - synthetic SFT data generator.
- `scripts/traces_to_sft.py` - convert saved traces into SFT rows.
- `scripts/train_lora.py` - LoRA/TRL training entrypoint.
- `modal/moku_modal.py` - Modal helpers for training and serving.
- `docs/` - Modal setup and hackathon badge notes.

## Hackathon Submission

| Link | URL |
|------|-----|
| **Live demo (HF Space)** | https://huggingface.co/spaces/build-small-hackathon/moku-the-first-word |
| **GitHub** | https://github.com/AravindMohan10/Moku-The-First-Word |
| **Modal vLLM (MiniCPM3-4B)** | https://m-aravind619--moku-the-first-word-serve.modal.run/v1 |
| **Open trace** | `data/traces/world-8953-t34-open-trace.json` (120 turns, all `provider: local`) |
| **Field notes** | [docs/FIELD_NOTES.md](docs/FIELD_NOTES.md) |

### HF Space secrets

Set these under **Settings → Repository secrets** on the Space:

```bash
HF_TOKEN=...
MEM0_API_KEY=...
MOKU_LLM_PROVIDER=auto
MOKU_HF_MODEL=openbmb/MiniCPM3-4B
MOKU_MODEL_BASE_URL=https://m-aravind619--moku-the-first-word-serve.modal.run/v1
MOKU_MODEL_API_KEY=local
MOKU_MEM0_RETRIEVE=local
```

## Hackathon Demo Arc

1. Open **Watch Forest**.
2. Stay in **Sandbox**.
3. Let the simulation run until the first visible glyphs spread.
4. Watch scarcity, strangers, danger, and rain pressure the creatures.
5. Open **Details** to show mind traces, memories, dictionary guesses, trust, and deception.
6. Press **Stop** for the forest epilogue.
7. Export JSON as proof of model choices.

## Codex Checkpoint

Stamped by Codex on 2026-06-13 as the immersive simulation checkpoint: two watch modes, model-load-bearing creature minds, Mem0-ready per-creature memory, JSON repair, trace evidence, and a forest-first UI.

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for the human + Codex attribution note.
