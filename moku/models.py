from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Action = Literal[
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


class CreatureTurn(BaseModel):
    action: Action
    target: str | None = None
    glyphs: list[str] = Field(min_length=1, max_length=3)
    intended_meaning: str
    interpretation: dict[str, str]
    memory_to_store: str
    trust_updates: dict[str, int]
    mood: str
    reasoning_summary: str

