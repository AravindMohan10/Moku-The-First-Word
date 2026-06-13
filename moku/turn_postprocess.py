"""Sanitize and coerce LLM creature turns before engine execution."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from moku.models import CreatureTurn

if TYPE_CHECKING:
    from moku.sim_engine import Creature, WorldState


def _creature_names(state: Any) -> set[str]:
    return {c.name for c in state.creatures}


def sanitize_memory(text: str, state: Any) -> str:
    """Drop memories that reference creatures not yet in the world."""
    if not text:
        return text
    valid = _creature_names(state)
    cleaned = text.strip()
    for match in re.findall(r"Stray-\d+", cleaned):
        if match not in valid:
            cleaned = re.sub(rf"[^.!?]*{re.escape(match)}[^.!?]*[.!?]?", "", cleaned).strip()
    for token in re.findall(r"\bStray-\d+\b", cleaned):
        if token not in valid:
            cleaned = re.sub(rf"[^.!?]*{re.escape(token)}[^.!?]*[.!?]?", "", cleaned).strip()
    if not cleaned:
        return f"I watched the forest on turn {state.turn}."
    return cleaned[:180]


def _adjacent(state: Any, c: Any) -> list[Any]:
    return [
        o
        for o in state.creatures
        if o.cid != c.cid and abs(o.x - c.x) + abs(o.y - c.y) <= 2
    ]


def coerce_share_food(c: Any, state: Any, turn: CreatureTurn) -> CreatureTurn:
    """Use engine share_food when the mind clearly intends feeding a nearby ally."""
    if turn.action == "share_food":
        return turn
    blob = f"{turn.intended_meaning} {turn.reasoning_summary}".lower()
    share_words = ("share food", "share_food", "feed ", "feeding", "giving food", "offered food")
    if turn.action != "signal" or c.food <= 0:
        return turn
    if not any(w in blob for w in share_words):
        return turn
    neighbors = _adjacent(state, c)
    if not neighbors:
        return turn
    names = {o.name for o in neighbors}
    target = turn.target if turn.target in names else None
    if not target:
        target = sorted(neighbors, key=lambda o: o.hunger, reverse=True)[0].name
    return turn.model_copy(update={"action": "share_food", "target": target})


def fix_targets(c: Any, state: Any, turn: CreatureTurn) -> CreatureTurn:
    valid = _creature_names(state)
    target = turn.target
    if target == c.name or (target and target not in valid):
        target = None
    if turn.action in {"follow", "signal", "share_food"} and not target:
        neighbors = _adjacent(state, c)
        if neighbors and turn.action == "follow":
            target = sorted(neighbors, key=lambda o: c.trust.get(o.name, 0), reverse=True)[0].name
    return turn.model_copy(update={"target": target})


def post_process_creature_turn(c: Any, state: Any, turn: CreatureTurn) -> CreatureTurn:
    turn = fix_targets(c, state, turn)
    turn = coerce_share_food(c, state, turn)
    mem = sanitize_memory(turn.memory_to_store, state)
    trust = {k: v for k, v in turn.trust_updates.items() if k in _creature_names(state)}
    return turn.model_copy(update={"memory_to_store": mem, "trust_updates": trust})
