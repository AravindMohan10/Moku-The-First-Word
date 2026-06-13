#!/usr/bin/env python3
"""
LoRA fine-tune Moku creature policy on trace-derived SFT data.

Requires: pip install -r requirements-train.txt
GPU recommended (Modal, Colab, or local CUDA).

Example:
  python scripts/traces_to_sft.py --input data/traces/world-8953-t22.json
  python scripts/train_lora.py --data data/moku_sft_from_traces.jsonl --output models/moku-lora
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA fine-tune Moku policy model")
    parser.add_argument("--data", default="data/moku_sft_from_traces.jsonl")
    parser.add_argument("--base-model", default="meta-llama/Llama-3.2-3B-Instruct")
    parser.add_argument("--output", default="models/moku-lora")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-samples", type=int, default=0, help="0 = all")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"Missing {data_path}. Run: python scripts/traces_to_sft.py")

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from trl import SFTTrainer
    except ImportError as exc:
        raise SystemExit(
            "Install training deps: pip install -r requirements-train.txt\n"
            f"Import error: {exc}"
        ) from exc

    rows: list[dict] = []
    with data_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    if args.max_samples:
        rows = rows[: args.max_samples]
    if len(rows) < 10:
        raise SystemExit(f"Need at least 10 rows; found {len(rows)}. Export more traces first.")

    def format_row(row: dict) -> dict:
        text_parts: list[str] = []
        for msg in row["messages"]:
            text_parts.append(f"### {msg['role']}\n{msg['content']}")
        return {"text": "\n\n".join(text_parts)}

    dataset = Dataset.from_list([format_row(r) for r in rows])

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
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

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.lr,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        bf16=torch.cuda.is_available(),
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    trainer.train()
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    print(f"Saved LoRA adapter to {out_dir}")
    print("Serve with: MOKU_MODEL_BASE_URL=<your-vllm-or-llama-cpp-url> MOKU_MODEL_NAME=<merged-or-base>")


if __name__ == "__main__":
    main()
