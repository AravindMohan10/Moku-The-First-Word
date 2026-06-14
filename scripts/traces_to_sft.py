#!/usr/bin/env python3
"""Build SFT JSONL from exported mind traces (matches live sim prompt)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from moku.models import CreatureTurn

SYSTEM_PROMPT = (
    "You are the policy mind of a tiny forest creature in a glyph-only society. "
    "Invent 1-3 short glyph words per turn (2-8 lowercase letters, not English, not creature names). "
    "Reuse glyphs from public_glyphs or nearby last_glyphs when context repeats; "
    "coin a fresh glyph when overused_glyphs dominates or the situation is new. "
    "Use share_food (with target) when you hold food and a nearby ally is hungry — not signal. "
    "target must be a name from valid_creature_names, never yourself. "
    "Under scarcity, you may deceive with misleading glyphs. "
    "Choose one legal action. Return strict JSON only with keys: "
    "action, target, glyphs, intended_meaning, interpretation, memory_to_store, "
    "trust_updates, mood, reasoning_summary."
)


def trace_to_messages(row: dict) -> dict | None:
    if row.get("fallback"):
        return None
    creature = row.get("creature")
    action = row.get("action")
    glyphs = row.get("glyphs") or []
    if not creature or not action or not glyphs:
        return None
    try:
        assistant = CreatureTurn(
            action=action,
            target=row.get("target"),
            glyphs=glyphs[:3],
            intended_meaning=str(row.get("intended_meaning") or row.get("reasoning_summary") or "local signal")[:200],
            interpretation=row.get("interpretation") if isinstance(row.get("interpretation"), dict) else {},
            memory_to_store=str(row.get("memory_to_store") or "")[:180],
            trust_updates={},
            mood=str(row.get("mood") or "calm"),
            reasoning_summary=str(row.get("reasoning_summary") or "Acted from observation and memory.")[:240],
        )
    except Exception:
        return None

    user_obs = {
        "creature": creature,
        "turn": row.get("turn"),
        "action_taken_context": {
            "target": row.get("target"),
            "glyphs": glyphs,
            "mood": row.get("mood"),
        },
        "note": "Reconstructed from golden trace; train policy to reproduce JSON decisions.",
    }
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Turn observation:\n{json.dumps(user_obs, ensure_ascii=True)}"},
            {"role": "assistant", "content": assistant.model_dump_json()},
        ]
    }


def load_traces(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    return list(raw.get("trace_log") or [])


GOLDEN_TRACE_FILES = (
    "world-8953-t19.json",
    "world-8953-t22.json",
    "world-8953-t33.json",
    "world-8953-t34-open-trace.json",
    "world-7118-t18.json",
)


def pick_latest_snapshots(paths: list[Path]) -> list[Path]:
    """Keep one file per world — highest turn number (avoids t1..t18 duplicate rows)."""
    best: dict[str, tuple[Path, int]] = {}
    for path in paths:
        match = re.match(r"(world-\d+)-t(\d+)\.json$", path.name)
        if not match:
            continue
        world, turn = match.group(1), int(match.group(2))
        if world not in best or turn > best[world][1]:
            best[world] = (path, turn)
    if best:
        return [pair[0] for pair in sorted(best.values(), key=lambda x: x[1])]
    return paths


def pick_training_files(paths: list[Path], *, all_snapshots: bool) -> list[Path]:
    if all_snapshots:
        return paths
    golden = [p for p in paths if p.name in GOLDEN_TRACE_FILES and p.exists()]
    if golden:
        return sorted(golden, key=lambda p: p.name)
    return pick_latest_snapshots(paths)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert Moku trace JSON exports to SFT JSONL")
    parser.add_argument(
        "--input",
        nargs="*",
        default=["data/traces"],
        help="Trace files or directories (default: data/traces)",
    )
    parser.add_argument("--output", default="data/moku_sft_from_traces.jsonl")
    parser.add_argument(
        "--all-snapshots",
        action="store_true",
        help="Include every t1, t2, … file (duplicates — not recommended)",
    )
    args = parser.parse_args()

    paths: list[Path] = []
    for item in args.input:
        p = Path(item)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.json")))
        elif p.is_file():
            paths.append(p)

    if args.all_snapshots:
        use_paths = paths
    else:
        use_paths = pick_training_files(paths, all_snapshots=False)
        if use_paths:
            print("Training files:", ", ".join(p.name for p in use_paths))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    seen_keys: set[tuple] = set()
    with out_path.open("w", encoding="utf-8") as f:
        for path in use_paths:
            for row in load_traces(path):
                key = (row.get("turn"), row.get("creature"), row.get("action"), tuple(row.get("glyphs") or []))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                msg = trace_to_messages(row)
                if not msg:
                    continue
                f.write(json.dumps(msg, ensure_ascii=True) + "\n")
                written += 1
    print(f"Wrote {written} training rows to {out_path} from {len(use_paths)} file(s)")


if __name__ == "__main__":
    main()
