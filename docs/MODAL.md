# Modal deployment for Moku

## Prerequisites

1. **Traces already in repo** — `data/traces/world-8953-t19.json` ✓ (plus other snapshots)
2. **Modal account** — [modal.com](https://modal.com) ($250 credits)
3. **HF token** — for gated Llama weights

```bash
pip install modal
modal token new
modal secret create huggingface HF_TOKEN=hf_your_token_here
```

## Step 1 — Build SFT dataset (local)

```bash
cd /Users/aravindmohan/Moku-The-First-Word
source .venv/bin/activate   # or your venv
python scripts/traces_to_sft.py --input data/traces
# → data/moku_sft_from_traces.jsonl (~240 rows from world-8953-t22 + world-7118-t18)
```

Uses **latest snapshot per world** only (not duplicate t1…t18 files).

## Step 2 — Train LoRA on Modal GPU

```bash
modal run modal/moku_modal.py::train
```

- Runs on **A10G** (~15–30 min for 1 epoch)
- Saves merged model to Modal volume `moku-models`
- Hackathon **fine-tuning badge** ✓

Optional: `modal run modal/moku_modal.py::train --epochs 2`

## Step 3 — Serve inference on Modal

```bash
modal serve modal/moku_modal.py
```

Modal prints a URL like `https://you--moku-the-first-word-serve.modal.run`

## Step 4 — Point Moku app at Modal

Add to `.env`:

```bash
MOKU_LLM_PROVIDER=local
MOKU_MODEL_BASE_URL=https://YOU--moku-the-first-word-serve.modal.run/v1
MOKU_MODEL_NAME=meta-llama/Llama-3.2-3B-Instruct
# Optional: stop HF billing while Modal runs
# MOKU_HF_TOKEN=
```

Restart:

```bash
python app.py
```

Top bar should show `local/meta-llama/Llama-3.2-3B-Instruct`.

## Replay mode (no LLM cost for judge demo)

```bash
MOKU_REPLAY_TRACES=data/traces/world-8953-t19.json
```

## Costs

- **Train:** one A10G hour ≈ few dollars of Modal credit
- **Serve:** billed while `modal serve` runs — **stop it** when not demoing
- **HF Inference:** can disable once Modal works

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `huggingface` secret missing | `modal secret create huggingface HF_TOKEN=...` |
| No SFT file on Modal | Run `traces_to_sft.py` locally first (mounted with repo) |
| vLLM OOM | Reduce `--max-model-len` in `moku_modal.py` |
| Llama 403 | Accept license on HF model page with same token |
