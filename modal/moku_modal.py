"""
Moku on Modal — LoRA fine-tune from trace SFT data, then serve OpenAI-compatible API.

Setup (once):
  pip install modal
  modal token new
  modal secret create huggingface HF_TOKEN=hf_...

Build SFT data locally first:
  python scripts/traces_to_sft.py --input data/traces

Train on Modal GPU:
  modal run modal/moku_modal.py::train

Serve vLLM (keep running for demo):
  modal serve modal/moku_modal.py

Then in .env:
  MOKU_LLM_PROVIDER=local
  MOKU_MODEL_BASE_URL=https://<your-modal-url>/v1
  MOKU_HF_MODEL=openbmb/MiniCPM3-4B
  MOKU_BASE_MODEL=openbmb/MiniCPM3-4B
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import modal

APP_NAME = "moku-the-first-word"
VOLUME_NAME = "moku-models"
BASE_MODEL = os.environ.get("MOKU_BASE_MODEL", "openbmb/MiniCPM3-4B")

app = modal.App(APP_NAME)
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

repo_root = Path(__file__).resolve().parents[1]

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-devel-ubuntu22.04", add_python="3.11")
    .entrypoint([])
    .pip_install(
        "torch>=2.2.0",
        "transformers>=4.44.0",
        "peft>=0.12.0",
        "trl>=0.9.0",
        "datasets>=2.20.0",
        "accelerate>=0.33.0",
        "huggingface_hub>=0.26.0",
        "vllm>=0.6.0",
        "sentencepiece",
        "protobuf",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .add_local_file(
        repo_root / "data" / "moku_sft_from_traces.jsonl",
        remote_path="/root/data/moku_sft_from_traces.jsonl",
    )
    .add_local_dir(
        repo_root / "moku",
        remote_path="/root/moku/moku",
    )
)

@app.function(
    image=image,
    gpu="A10G",
    timeout=60 * 60,
    volumes={"/models": volume},
    secrets=[modal.Secret.from_name("huggingface")],
)
def train(
    data_path: str = "/root/data/moku_sft_from_traces.jsonl",
    epochs: int = 1,
    max_samples: int = 0,
) -> str:
    """LoRA fine-tune on trace SFT JSONL; merge adapter; save to Modal volume."""
    import torch
    from datasets import Dataset
    from huggingface_hub import login
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
    from trl import SFTTrainer

    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if hf_token:
        login(token=hf_token)

    path = Path(data_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}. Run locally: python scripts/traces_to_sft.py"
        )

    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    if max_samples:
        rows = rows[:max_samples]
    if len(rows) < 10:
        raise ValueError(f"Need >=10 rows, got {len(rows)}")

    def format_row(row: dict) -> dict:
        parts = [f"### {m['role']}\n{m['content']}" for m in row["messages"]]
        return {"text": "\n\n".join(parts)}

    dataset = Dataset.from_list([format_row(r) for r in rows])
    print(f"Training on {len(dataset)} examples")

    lora_dir = Path("/models/moku-lora")
    merged_dir = Path("/models/moku-merged")
    lora_dir.mkdir(parents=True, exist_ok=True)
    merged_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, token=hf_token, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        token=hf_token,
        trust_remote_code=True,
    )
    lora = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    )
    model = get_peft_model(model, lora)

    training_args = TrainingArguments(
        output_dir=str(lora_dir),
        num_train_epochs=epochs,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=5,
        save_strategy="epoch",
        report_to="none",
        bf16=True,
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    trainer.train()
    model.save_pretrained(lora_dir)
    tokenizer.save_pretrained(lora_dir)

    print("Merging LoRA into base for vLLM…")
    base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        token=hf_token,
        trust_remote_code=True,
    )
    merged = PeftModel.from_pretrained(base, str(lora_dir))
    merged = merged.merge_and_unload()
    merged.save_pretrained(merged_dir)
    tokenizer.save_pretrained(merged_dir)
    volume.commit()
    return str(merged_dir)


@app.function(
    image=image,
    gpu="A10G",
    timeout=24 * 60 * 60,
    volumes={"/models": volume},
    secrets=[modal.Secret.from_name("huggingface")],
)
@modal.concurrent(max_inputs=8)
@modal.web_server(8000, startup_timeout=600)
def serve() -> None:
    """OpenAI-compatible vLLM server — point MOKU_MODEL_BASE_URL here."""
    import subprocess

    model_path = "/models/moku-merged"
    if not Path(model_path).exists():
        model_path = BASE_MODEL

    cmd = [
        "python",
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        model_path,
        "--trust-remote-code",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--dtype",
        "bfloat16",
        "--max-model-len",
        "2048",
        "--enforce-eager",
    ]
    print("Starting vLLM:", " ".join(cmd))
    subprocess.Popen(" ".join(cmd), shell=True)
