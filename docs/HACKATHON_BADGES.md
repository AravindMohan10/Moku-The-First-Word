# Moku — Trophy cabinet & merit badge map

Goal: stack **OpenBMB Awards**, **Thousand Token Wood**, **Tiny Titan**, and as many merit badges as possible without sacrificing demo quality.

## Model choice (OpenBMB)

OpenBMB does not ship an exact **3B** checkpoint. Use:

| Model | Params | Why |
|-------|--------|-----|
| **`openbmb/MiniCPM3-4B`** | 4B | **Primary pick** — strong JSON/function calling, beats many 7B baselines; still ≤4B for Tiny Titan |
| `openbmb/MiniCPM5-1B` | 1B | Smaller sponsor flagship; use only if you need extreme speed over quality |

**Important:** OpenBMB weights are **not** on Hugging Face Inference Providers for most accounts. For a real OpenBMB judge demo, serve via **Modal vLLM** (or local vLLM/llama.cpp) — not HF-hosted inference alone.

## Merit badges (sash)

| Badge | Label | Status | How to earn |
|-------|-------|--------|-------------|
| Off the Grid | LOCAL-FIRST | 🟡 | `MOKU_MODEL_BASE_URL` → Modal vLLM or local server (no cloud LLM API at demo time) |
| Off-Brand | CUSTOM UI | ✅ | Observatory CSS + custom HTML panels (not default Gradio chrome) |
| Sharing is Caring | OPEN TRACE | ⬜ | Upload `data/traces/world-8953-t34-open-trace.json` to a public HF dataset/repo |
| Well-Tuned | FINE-TUNED | 🟡 | `traces_to_sft.py` → `train_lora.py` on MiniCPM3-4B → publish LoRA on HF |
| Llama Champion | LLAMA.CPP | ⬜ | Optional second demo path with GGUF + llama.cpp (conflicts with OpenBMB pitch — skip unless chasing max badges) |
| Field Notes | TENTATIVE | ⬜ | Blog post / build report linked from README |

**Realistic stack without quality loss:** LOCAL-FIRST + CUSTOM UI + OPEN TRACE + FINE-TUNED + Field Notes = **5 badges** while running MiniCPM3-4B on Modal.

## Cash awards we can target

| Award | Track | Our angle |
|-------|-------|-----------|
| **OpenBMB Awards** (up to $2.5k/track) | Backyard + TTW | MiniCPM3-4B base + optional LoRA from golden traces; Modal serve |
| **Thousand Token Wood** podium | TTW | ≤4B agent, Mem0 memory, inspectable traces, emergence story |
| **Tiny Titan** ($1k) | Special | MiniCPM3-4B or MiniCPM5-1B — call out param count on homepage |
| **Modal Awards** (credits) | Sponsor | `modal/moku_modal.py` train + serve |
| **Off-Brand** ($1.5k) | Special | Observatory UI + `gr.Server` if you want extra polish |
| **Best Agent** ($1k) | Special | Six parallel creature minds, JSON schema, Mem0, trace export |
| **Bonus Quest Champion** ($2k) | Special | Max badge stack above |
| **Community Choice** ($2k) | HF vote | Strong 2-min demo + social post |

## Core requirements (must have)

| Requirement | Status | Proof |
|-------------|--------|-------|
| Small model (≤4B cap) | ✅ | `openbmb/MiniCPM3-4B` |
| Mem0 memory | ✅ | Per-creature namespaces; `memories_retrieved` in Mind Traces |
| Gradio UI | ✅ | `python app.py` |
| Inspectability | ✅ | Mind Traces + JSON export |

## Recommended demo stack (quality preserved)

### 1. Serve OpenBMB on Modal (judge path)

```bash
# Build SFT from golden trace
python scripts/traces_to_sft.py --input data/traces/world-8953-t33.json

# Train + serve (needs modal token + huggingface secret)
modal run modal/moku_modal.py::train
modal serve modal/moku_modal.py
```

In `.env`:

```bash
MOKU_HF_MODEL=openbmb/MiniCPM3-4B
MOKU_LLM_PROVIDER=auto
MOKU_MODEL_BASE_URL=https://<workspace>--moku-the-first-word-serve.modal.run/v1
MOKU_MODEL_API_KEY=local
```

Mind Traces should show `provider: local`, `model: openbmb/MiniCPM3-4B`.

### 2. HF fallback (local dev only)

When Modal is down, `auto` falls back to `Qwen/Qwen2.5-Coder-3B-Instruct` on HF Inference (same model family as `world-8953-t33.json`). **Do not submit with Qwen as primary** if targeting OpenBMB Awards.

### 3. Fine-tune for Well-Tuned badge

```bash
python scripts/traces_to_sft.py --input data/traces/world-8953-t33.json
python scripts/train_lora.py --base-model openbmb/MiniCPM3-4B --data data/moku_sft_from_traces.jsonl
# Publish adapter to HF: your-org/moku-minicpm3-4b-lora
```

Re-train on Modal with `MOKU_BASE_MODEL=openbmb/MiniCPM3-4B`; merged weights land in `/models/moku-merged`.

### 4. Replay mode (bulletproof booth)

```bash
MOKU_REPLAY_TRACES=data/traces/world-8953-t33.json python app.py
```

Deterministic demo from a run that already has rich glyph drift — use if live LLM hiccups during judging.

## Golden demo script (2 min)

1. Home → real vs scripted + model line shows `local/openbmb/MiniCPM3-4B`
2. Sandbox → Play → Speech on
3. Turn 8: stranger + Signals overlay
4. Turn 14: Stop → Forest Epilogue
5. Mind Traces + JSON export
6. Details → Glyph Drift + Social Graph

## Submission checklist

- [ ] Modal URL live during judging OR replay trace ready
- [ ] 2-minute screen recording
- [ ] HF Space or public Gradio link
- [ ] Trace JSON on Hub (`OPEN TRACE`)
- [ ] LoRA adapter on Hub (`FINE-TUNED`) — optional but high value
- [ ] README links here + OpenBMB model id + Mem0
- [ ] Blog / Field Notes post

## Honest pitch

> Moku is a fixed-seed forest stage with OpenBMB MiniCPM3-4B minds (4B, not cloud APIs at demo time). Words emerge because minds reuse what they hear — check Glyph Drift for conflicting meanings. We fine-tuned on our own golden traces. Mind Traces are the proof; chronicle is narration.
