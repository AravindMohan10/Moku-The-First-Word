from __future__ import annotations

import json
import random
from pathlib import Path

from moku.models import CreatureTurn

OUT_PATH = Path("moku_sft_2000.jsonl")
GLYPHS = ["moku", "tala", "nim", "ra", "veli", "soma", "pav", "zhi", "koro", "lune"]
NAMES = ["Lumo", "Nia", "Oro", "Pika", "Vey", "Sora", "Miri", "Tiko"]
TRAITS = ["curious", "selfish", "loyal", "anxious", "brave", "mischievous", "gentle", "cunning"]
ACTIONS = [
    "move_north",
    "move_south",
    "move_east",
    "move_west",
    "stay",
    "gather",
    "hide",
    "follow",
    "signal",
    "share_food",
]


def sample_example(r: random.Random) -> dict:
    creature = r.choice(NAMES)
    friend = r.choice([n for n in NAMES if n != creature])
    glyph = r.choice(GLYPHS)
    glyph2 = r.choice([g for g in GLYPHS if g != glyph])
    hunger = r.choice(["low", "mid", "high"])
    fear = r.choice(["low", "mid", "high"])
    action = r.choice(ACTIONS)
    if action == "follow":
        target = friend
    else:
        target = None
    glyphs = [glyph] if r.random() < 0.6 else [glyph, glyph2][: r.randint(1, 2)]
    assistant_obj = CreatureTurn(
        action=action,  # type: ignore[arg-type]
        target=target,
        glyphs=glyphs,
        intended_meaning=r.choice(
            [
                "food nearby, follow me",
                "danger nearby, stay alert",
                "come toward shelter",
                "I am testing a social signal",
            ]
        ),
        interpretation={r.choice(GLYPHS): r.choice(["food maybe", "danger maybe", "follow maybe"])},
        memory_to_store=f"I used {' '.join(glyphs)} and watched {friend} react.",
        trust_updates={friend: r.choice([-1, 0, 1])},
        mood=r.choice(["eager", "wary", "calm", "scheming"]),
        reasoning_summary="I used local observation, memory, and trust to choose action and glyph.",
    )
    prompt = (
        f"Creature: {creature}\n"
        f"Personality: {r.choice(TRAITS)}, {r.choice(TRAITS)}\n"
        f"Hunger: {hunger}\n"
        f"Fear: {fear}\n"
        f"Visible world: food maybe east, danger maybe west, shelter maybe south.\n"
        f"Recent memories: I used {glyph} before and {friend} reacted.\n"
        f"Known glyph beliefs: {glyph} uncertain.\n"
        f"Trust: {friend} {r.choice(['+2', '+1', '0', '-1'])}.\n"
        f"Legal actions: {', '.join(ACTIONS)}."
    )
    return {
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the policy mind of a tiny forest creature. "
                    "Speak only in 1-3 glyphs and choose one legal action. Return strict JSON only."
                ),
            },
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": assistant_obj.model_dump_json()},
        ]
    }


def main(n: int = 2000, seed: int = 17) -> None:
    r = random.Random(seed)
    rows = [sample_example(r) for _ in range(n)]
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
    print(f"Wrote {n} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()

