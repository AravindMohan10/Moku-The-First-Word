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

Hugging Face provider:

```bash
HF_TOKEN=...
MOKU_LLM_PROVIDER=auto
MOKU_HF_MODEL=openbmb/MiniCPM5-1B
```

Local OpenAI-compatible provider:

```bash
MOKU_LLM_PROVIDER=local
MOKU_MODEL_BASE_URL=http://127.0.0.1:8080/v1
MOKU_MODEL_NAME=meta-llama/Llama-3.2-3B-Instruct
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
