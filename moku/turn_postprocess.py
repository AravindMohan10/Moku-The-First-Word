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


def _visible_food(c: Any, state: Any) -> list[tuple[int, int]]:
    return [
        (x, y)
        for x, y in state.food
        if abs(x - c.x) + abs(y - c.y) <= 2
    ]


def _dir_toward(cx: int, cy: int, tx: int, ty: int) -> str:
    if tx > cx:
        return "move_east"
    if tx < cx:
        return "move_west"
    if ty > cy:
        return "move_south"
    if ty < cy:
        return "move_north"
    return "gather"


def _free_moves(c: Any, state: Any) -> list[str]:
    moves: list[str] = []
    for nx, ny, action in (
        (c.x, c.y - 1, "move_north"),
        (c.x, c.y + 1, "move_south"),
        (c.x + 1, c.y, "move_east"),
        (c.x - 1, c.y, "move_west"),
    ):
        if not (0 <= nx < state.width and 0 <= ny < state.height):
            continue
        blocked = any(o.x == nx and o.y == ny and o.cid != c.cid for o in state.creatures)
        if not blocked:
            moves.append(action)
    return moves


def coerce_movement(c: Any, state: Any, turn: CreatureTurn) -> CreatureTurn:
    """Nudge idle minds to roam — share_food clusters creatures; movement keeps the forest alive."""
    if turn.action in {"move_north", "move_south", "move_east", "move_west", "follow", "gather", "hide", "share_food"}:
        return turn
    food = _visible_food(c, state)
    if food and c.hunger >= 40 and (c.x, c.y) not in state.food:
        tx, ty = min(food, key=lambda p: abs(p[0] - c.x) + abs(p[1] - c.y))
        action = _dir_toward(c.x, c.y, tx, ty)
        free = _free_moves(c, state)
        if action == "gather" and (c.x, c.y) in state.food:
            return turn.model_copy(update={"action": "gather"})
        if action in free:
            return turn.model_copy(update={"action": action})
        if free:
            return turn.model_copy(update={"action": free[0]})
    if turn.action in ("stay", "signal"):
        free = _free_moves(c, state)
        if free and (c.hunger >= 35 or len(_adjacent(state, c)) <= 1):
            return turn.model_copy(update={"action": free[0]})
    return turn


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
    neighbors = _adjacent(state, c)
    if turn.action in {"follow", "signal", "share_food"} and not target:
        strangers = [o for o in neighbors if str(o.name).startswith("Stray")]
        if strangers and getattr(state, "scarcity_level", 0) >= 2:
            target = strangers[0].name
        elif neighbors and turn.action == "follow":
            target = sorted(neighbors, key=lambda o: c.trust.get(o.name, 0), reverse=True)[0].name
        elif neighbors and turn.action == "share_food" and c.food > 0:
            hungry = sorted(neighbors, key=lambda o: o.hunger, reverse=True)
            target = hungry[0].name if hungry else None
    return turn.model_copy(update={"target": target})


def post_process_creature_turn(c: Any, state: Any, turn: CreatureTurn) -> CreatureTurn:
    turn = fix_targets(c, state, turn)
    turn = coerce_share_food(c, state, turn)
    turn = coerce_movement(c, state, turn)
    mem = sanitize_memory(turn.memory_to_store, state)
    trust = {k: v for k, v in turn.trust_updates.items() if k in _creature_names(state)}
    return turn.model_copy(update={"memory_to_store": mem, "trust_updates": trust})
