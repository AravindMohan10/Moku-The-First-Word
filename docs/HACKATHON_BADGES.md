# Moku — Thousand Token Wood badge checklist

Stack these for maximum hackathon score. Each item maps to something judges can **see or run**.

## Core requirements (must have)

| Badge | Status | Proof |
|-------|--------|--------|
| **Small model (<4B)** | ✅ | `MOKU_HF_MODEL=meta-llama/Llama-3.2-3B-Instruct` in `.env` |
| **Mem0 memory** | ✅ | Per-creature namespaces; show `memories_retrieved` in Mind Traces |
| **Gradio UI** | ✅ | `python app.py` |
| **Inspectability** | ✅ | Mind Traces + ⬇ JSON export (full world payload) |

## Extra points (implemented in repo)

| Badge | How | Demo line |
|-------|-----|-----------|
| **Fine-tuning / SFT** | `scripts/traces_to_sft.py` → `scripts/train_lora.py` | “We fine-tune on our own golden traces, not synthetic English.” |
| **Local inference** | `MOKU_MODEL_BASE_URL` + Modal / llama.cpp | “Unlimited demo runs without HF billing.” |
| **Replay mode** | `MOKU_REPLAY_TRACES=data/traces/world-8953-t22.json` | “Deterministic judge demo from recorded minds.” |
| **Emergence honesty** | Home page “real vs scripted” | “Sandbox stage is fixed; language and alliances are LLM.” |
| **Glyph drift viz** | Details → Glyph Drift | Same glyph, conflicting readings in traces |
| **Social graph** | Details → Social Graph | Oro→Lumo signal counts |

## Fine-tuning pipeline (quick)

```bash
# 1. Run sandbox, export JSON at turn 14+, Stop for epilogue
# 2. Build dataset from real traces
python scripts/traces_to_sft.py --input data/traces/world-8953-t22.json

# 3. Train LoRA (GPU — Modal recommended)
pip install -r requirements-train.txt
python scripts/train_lora.py --data data/moku_sft_from_traces.jsonl --output models/moku-lora
```

## Local / Modal inference

```bash
# llama.cpp or vLLM OpenAI-compatible server
export MOKU_LLM_PROVIDER=local
export MOKU_MODEL_BASE_URL=http://127.0.0.1:8080/v1
export MOKU_MODEL_NAME=meta-llama/Llama-3.2-3B-Instruct
python app.py
```

## Golden demo script (2 min)

1. Home → explain real vs scripted  
2. Sandbox → Play → Speech on  
3. Turn 8: stranger + Signals overlay  
4. Turn 14: Stop → Forest Epilogue  
5. Open Mind Traces + ⬇ JSON  
6. Details → Glyph Drift + Social Graph  

## Submission assets

- [ ] 2-minute screen recording  
- [ ] HF Space or public Gradio link  
- [ ] One exported trace JSON attached  
- [ ] README links to this file + model name + Mem0  

## Honest pitch (use verbatim if stuck)

> Moku is a fixed-seed forest stage with LLM-controlled minds. Words emerge because minds reuse what they hear — check Glyph Drift for conflicting meanings. Mind Traces are the proof; chronicle is narration.
