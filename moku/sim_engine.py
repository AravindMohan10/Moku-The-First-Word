from __future__ import annotations

import html
import json
import os
import random
import re
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from moku.json_repair import parse_creature_turn, repair_creature_payload
from moku.llm_client import (
    chat_json,
    default_model,
    provider_label,
    summarize_run_finale,
    summarize_run_finale_repair,
    summarize_turn_chronicle,
)
from moku.memory import get_memory_store
from moku.models import CreatureTurn
from moku.turn_postprocess import post_process_creature_turn

LEGAL_ACTIONS = [
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

PERSONALITIES = [
    "curious",
    "selfish",
    "loyal",
    "anxious",
    "brave",
    "mischievous",
    "gentle",
    "cunning",
    "patient",
]
GLYPH_FRAGMENTS = ["mo", "ku", "ta", "la", "ni", "ra", "ve", "li", "so", "pa", "ko", "lu", "ne", "zi", "br", "or"]
CREATURE_NAMES = ["Lumo", "Nia", "Oro", "Pika", "Vey", "Sora", "Miri", "Tiko", "Brum", "Eli"]
MOODS = ["eager", "wary", "hungry", "joyful", "uneasy", "scheming", "calm"]


def _invent_glyph(r: random.Random) -> str:
    parts = [r.choice(GLYPH_FRAGMENTS) for _ in range(r.randint(2, 3))]
    return "".join(parts)[:10]


def _invent_glyphs(r: random.Random, count: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < count:
        glyph = _invent_glyph(r)
        if glyph not in seen:
            seen.add(glyph)
            out.append(glyph)
    return out


def _is_glyph_token(token: str) -> bool:
    t = token.strip().lower()
    return 2 <= len(t) <= 12 and t.isalpha()


def _normalize_glyph(token: str) -> str:
    return token.strip().lower()[:12]


@dataclass
class Creature:
    cid: str
    name: str
    x: int
    y: int
    personality: list[str]
    hunger: int
    fear: int
    energy: int
    food: int = 0
    trust: dict[str, int] = field(default_factory=dict)
    glyph_beliefs: dict[str, float] = field(default_factory=dict)
    memories: list[str] = field(default_factory=list)
    last_action: str = "stay"
    last_glyphs: list[str] = field(default_factory=list)
    mood: str = "calm"


@dataclass
class WorldState:
    world_id: str
    width: int
    height: int
    turn: int
    mode: str
    creatures: list[Creature]
    food: set[tuple[int, int]]
    danger: set[tuple[int, int]]
    shelter: set[tuple[int, int]]
    transcript: list[str]
    dictionary_stats: dict[str, dict[str, int]]
    deception_events: list[str]
    field_notes: list[str]
    weather: str = "clear"
    scarcity_level: int = 0
    last_events: list[str] = field(default_factory=list)
    watch_mode: str = "sandbox"
    action_cursor: int = 0
    trace_log: list[dict[str, Any]] = field(default_factory=list)
    glyph_history: dict[str, dict[str, Any]] = field(default_factory=dict)
    evolution_notes: list[str] = field(default_factory=list)
    chronicle_log: list[dict[str, Any]] = field(default_factory=list)
    run_summary: dict[str, Any] | None = None
    replay_traces: list[dict[str, Any]] | None = None
    playing: bool = True
    prefetch_cid: str | None = None
    prefetch_plan: tuple[CreatureTurn, dict[str, Any]] | None = None


_prefetch_lock = threading.Lock()


def _bounded(v: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, v))


def _rng(seed: int | None = None) -> random.Random:
    return random.Random(seed if seed is not None else random.randint(1, 999_999))


def _spawn_points(r: random.Random, width: int, height: int, n: int) -> list[tuple[int, int]]:
    all_cells = [(x, y) for y in range(height) for x in range(width)]
    r.shuffle(all_cells)
    return all_cells[:n]


def _default_creature_mode() -> str:
    return "llm"


def _seed_creature_memories(state: WorldState) -> None:
    store = get_memory_store()
    for c in state.creatures:
        for mem in c.memories:
            store.add_memory(state.world_id, c.cid, mem, metadata={"seed": True})


def create_world(
    seed: int | None = None,
    mode: str | None = None,
    size: int = 9,
    n_creatures: int = 8,
    watch_mode: str = "sandbox",
) -> WorldState:
    r = _rng(seed)
    if mode is None:
        mode = _default_creature_mode()
    points = _spawn_points(r, size, size, n_creatures + 24)
    world_whispers = _invent_glyphs(r, max(8, n_creatures + 2))
    creatures: list[Creature] = []
    for i in range(n_creatures):
        x, y = points[i]
        personality = r.sample(PERSONALITIES, k=2)
        private_glyphs = r.sample(world_whispers, k=min(4, len(world_whispers)))
        c = Creature(
            cid=f"c{i}",
            name=CREATURE_NAMES[i % len(CREATURE_NAMES)],
            x=x,
            y=y,
            personality=personality,
            hunger=r.randint(20, 65),
            fear=r.randint(10, 40),
            energy=r.randint(55, 90),
            glyph_beliefs={g: round(r.uniform(0.2, 0.8), 2) for g in private_glyphs},
            memories=["I heard an unnamed murmur near shelter."],
        )
        creatures.append(c)

    for c in creatures:
        c.trust = {other.name: r.randint(-2, 3) for other in creatures if other.cid != c.cid}

    food = set(points[n_creatures : n_creatures + 10])
    danger = set(points[n_creatures + 10 : n_creatures + 16])
    shelter = set(points[n_creatures + 16 : n_creatures + 20])
    state = WorldState(
        world_id=f"world-{r.randint(1000, 9999)}",
        width=size,
        height=size,
        turn=0,
        mode=mode,
        creatures=creatures,
        food=food,
        danger=danger,
        shelter=shelter,
        transcript=[],
        dictionary_stats={},
        deception_events=[],
        field_notes=["Field Note #1: First dawn in the forest. The creatures murmur symbols."],
        last_events=[],
        watch_mode=watch_mode,
    )
    _seed_creature_memories(state)
    return state


def create_for_watch_mode(watch_mode: str) -> WorldState:
    if watch_mode == "sandbox":
        state = create_world(seed=42, mode="llm", size=9, n_creatures=6, watch_mode="sandbox")
        state.field_notes = [
            "Field Note #1: Sandbox dawn. A sound with no meaning is about to become useful."
        ]
    else:
        seed = random.randint(100, 9999)
        state = create_world(seed=seed, mode="llm", size=9, n_creatures=6, watch_mode="emergence")
    replay_path = os.environ.get("MOKU_REPLAY_TRACES", "").strip()
    if replay_path:
        path = Path(replay_path)
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            traces = raw if isinstance(raw, list) else raw.get("trace_log") or []
            if traces:
                state.replay_traces = traces
    return state


def reset_world_memory(state: WorldState) -> None:
    get_memory_store().clear_world(state.world_id)


def apply_sandbox_events(state: WorldState) -> WorldState:
    if state.watch_mode != "sandbox":
        return state
    if state.turn == 2:
        state = add_food(state)
        state.last_events = ["A glimmer-fruit falls — first food signal opportunity."]
    elif state.turn == 5:
        state = trigger_scarcity(state)
        state.last_events.append("Scarcity whispers. Someone may lie soon.")
    elif state.turn == 8:
        state = introduce_stranger(state)
    elif state.turn == 11:
        state = add_danger(state)
        state.last_events.append("Thorns bloom beside old trails.")
    elif state.turn == 14:
        state = start_rain(state)
    return state


def _visible_cells(c: Creature, state: WorldState, radius: int = 2) -> set[tuple[int, int]]:
    cells = set()
    for y in range(max(0, c.y - radius), min(state.height, c.y + radius + 1)):
        for x in range(max(0, c.x - radius), min(state.width, c.x + radius + 1)):
            cells.add((x, y))
    return cells


def _neighbors(c: Creature, state: WorldState) -> list[tuple[int, int, str]]:
    return [
        (c.x, c.y - 1, "move_north"),
        (c.x, c.y + 1, "move_south"),
        (c.x + 1, c.y, "move_east"),
        (c.x - 1, c.y, "move_west"),
    ]


def _in_bounds(x: int, y: int, state: WorldState) -> bool:
    return 0 <= x < state.width and 0 <= y < state.height


def _creature_at(x: int, y: int, state: WorldState) -> Creature | None:
    for c in state.creatures:
        if c.x == x and c.y == y:
            return c
    return None


def _speech_for(c: Creature, state: WorldState, r: random.Random) -> list[str]:
    known = sorted(c.glyph_beliefs.items(), key=lambda kv: kv[1], reverse=True)
    picks = [k for k, _ in known[:2]] if known else _invent_glyphs(r, 1)
    if state.dictionary_stats:
        heard = sorted(state.dictionary_stats.items(), key=lambda kv: kv[1]["uses"], reverse=True)
        for glyph, _stats in heard[:3]:
            if glyph not in picks:
                picks.append(glyph)
                break
    if not picks:
        picks = _invent_glyphs(r, 1)
    return picks[:3]


def _rule_policy(c: Creature, state: WorldState, r: random.Random) -> CreatureTurn:
    visible = _visible_cells(c, state)
    seen_food = [(x, y) for (x, y) in state.food if (x, y) in visible]
    seen_danger = [(x, y) for (x, y) in state.danger if (x, y) in visible]
    nearby_creatures = [
        o for o in state.creatures if o.cid != c.cid and abs(o.x - c.x) + abs(o.y - c.y) <= 2
    ]
    glyphs = _speech_for(c, state, r)

    action = "stay"
    target = None
    if (c.x, c.y) in state.food:
        action = "gather"
    elif c.fear > 70 or (c.x, c.y) in state.danger:
        action = "hide" if (c.x, c.y) in state.shelter else "move_north"
    elif seen_food and c.hunger > 45:
        tx, ty = min(seen_food, key=lambda p: abs(p[0] - c.x) + abs(p[1] - c.y))
        if tx > c.x:
            action = "move_east"
        elif tx < c.x:
            action = "move_west"
        elif ty > c.y:
            action = "move_south"
        elif ty < c.y:
            action = "move_north"
        else:
            action = "gather"
    elif nearby_creatures and "loyal" in c.personality:
        trusted = sorted(nearby_creatures, key=lambda o: c.trust.get(o.name, 0), reverse=True)[0]
        action = "follow"
        target = trusted.name
        glyphs = ["ra", glyphs[0]][:2]
    elif seen_danger and "brave" not in c.personality:
        action = "signal"
        glyphs = _speech_for(c, state, r)[:1] or _invent_glyphs(r, 1)
    else:
        action = r.choice(["move_north", "move_south", "move_east", "move_west", "signal", "stay"])

    interpretation = {}
    if state.transcript and r.random() < 0.35:
        pool = list(c.glyph_beliefs.keys()) or list(state.dictionary_stats.keys()) or _invent_glyphs(r, 1)
        heard = r.choice(pool)
        interpretation[heard] = r.choice(["danger maybe", "food maybe", "follow maybe"])

    updates: dict[str, int] = {}
    if nearby_creatures:
        pick = r.choice(nearby_creatures)
        updates[pick.name] = r.choice([-1, 0, 1])

    return CreatureTurn(
        action=action,  # type: ignore[arg-type]
        target=target,
        glyphs=glyphs,
        intended_meaning="A local social or survival signal.",
        interpretation=interpretation,
        memory_to_store=f"I used {' '.join(glyphs)} while feeling {c.mood or 'alert'}.",
        trust_updates=updates,
        mood=r.choice(MOODS),
        reasoning_summary="I acted from nearby signs, memory traces, and mood.",
    )


def _random_policy(c: Creature, state: WorldState, r: random.Random) -> CreatureTurn:
    target = None
    if r.random() < 0.25:
        others = [o.name for o in state.creatures if o.cid != c.cid]
        target = r.choice(others) if others else None
    glyph_count = r.randint(1, 3)
    return CreatureTurn(
        action=r.choice(LEGAL_ACTIONS),  # type: ignore[arg-type]
        target=target,
        glyphs=_invent_glyphs(r, glyph_count),
        intended_meaning="Instinctive burst.",
        interpretation={},
        memory_to_store="The wind moved through us and I answered.",
        trust_updates={},
        mood=r.choice(MOODS),
        reasoning_summary="Random baseline mode.",
    )


def _memory_query(c: Creature, state: WorldState) -> str:
    bits = [
        f"glyph trust food danger hunger {c.hunger}",
        f"location {c.x} {c.y}",
        f"weather {state.weather} scarcity {state.scarcity_level}",
    ]
    if c.last_glyphs:
        bits.append(" ".join(c.last_glyphs))
    if state.transcript:
        bits.append(state.transcript[-1])
    return " ".join(bits)


def _retrieve_memories(c: Creature, state: WorldState, k: int | None = None) -> list[str]:
    if k is None:
        k = int(os.environ.get("MOKU_MEMORY_RETRIEVE_K", "5"))
    store = get_memory_store()
    query = _memory_query(c, state)
    hits = store.search_memory(state.world_id, c.cid, query, k=k)
    if hits:
        c.memories = hits[-12:]
        return hits
    return c.memories[-k:]


def _heard_glyphs(state: WorldState, c: Creature) -> dict[str, str]:
    heard: dict[str, str] = {}
    for line in state.transcript[-6:]:
        if ":" not in line or c.name in line.split(":", 1)[0]:
            continue
        glyph_part = line.split(":", 1)[1].strip()
        for token in glyph_part.split():
            if not _is_glyph_token(token):
                continue
            glyph = _normalize_glyph(token)
            belief = c.glyph_beliefs.get(glyph, 0.4)
            if belief >= 0.55:
                heard[glyph] = "useful signal maybe"
            elif belief <= 0.35:
                heard[glyph] = "suspicious maybe"
            else:
                heard[glyph] = "unknown meaning"
    return heard


def _public_glyphs(state: WorldState, limit: int = 14) -> list[str]:
    """Mix frequent, recent, and underused glyphs so one word does not monopoly the language."""
    ranked = sorted(
        state.dictionary_stats.items(),
        key=lambda kv: kv[1].get("uses", 0),
        reverse=True,
    )
    top = [g for g, _ in ranked[:4]]
    recent: list[str] = []
    for line in reversed(state.transcript[-10:]):
        if ":" not in line:
            continue
        for token in line.split(":", 1)[1].split():
            if not _is_glyph_token(token):
                continue
            g = _normalize_glyph(token)
            if g and g not in recent:
                recent.append(g)
            if len(recent) >= 5:
                break
        if len(recent) >= 5:
            break
    underused = [g for g, stats in sorted(ranked, key=lambda kv: kv[1].get("uses", 0)) if stats.get("uses", 0) <= 2][:5]
    out: list[str] = []
    for g in top + recent + underused:
        if g not in out:
            out.append(g)
        if len(out) >= limit:
            break
    return out


def _overused_glyphs(state: WorldState, threshold: int = 10) -> list[str]:
    return [
        g
        for g, stats in state.dictionary_stats.items()
        if stats.get("uses", 0) >= threshold
    ][:5]


def _is_stranger(creature: Any) -> bool:
    return str(getattr(creature, "name", "")).startswith("Stray")


def _stranger_names(state: WorldState) -> list[str]:
    return [c.name for c in state.creatures if _is_stranger(c)]


def _llm_policy(c: Creature, state: WorldState, r: random.Random) -> tuple[CreatureTurn, dict[str, Any]]:
    visible = _visible_cells(c, state)
    seen_food = [list(p) for p in state.food if p in visible]
    seen_danger = [list(p) for p in state.danger if p in visible]
    nearby = [
        {
            "name": o.name,
            "x": o.x,
            "y": o.y,
            "trust": c.trust.get(o.name, 0),
            "last_glyphs": o.last_glyphs,
            "is_stranger": _is_stranger(o),
        }
        for o in state.creatures
        if o.cid != c.cid and abs(o.x - c.x) + abs(o.y - c.y) <= 3
    ]
    strangers_nearby = [n for n in nearby if n.get("is_stranger")]
    retrieved = _retrieve_memories(c, state)
    obs = {
        "creature": c.name,
        "personality": c.personality,
        "mood": c.mood,
        "hunger": c.hunger,
        "fear": c.fear,
        "energy": c.energy,
        "location": [c.x, c.y],
        "weather": state.weather,
        "scarcity_level": state.scarcity_level,
        "visible_food": seen_food,
        "visible_danger": seen_danger,
        "visible_shelter": [list(p) for p in state.shelter if p in visible],
        "nearby_creatures": nearby,
        "is_stranger": _is_stranger(c),
        "strangers_in_world": _stranger_names(state),
        "strangers_nearby": strangers_nearby,
        "glyph_beliefs": c.glyph_beliefs,
        "trust": c.trust,
        "retrieved_memories": retrieved,
        "heard_glyphs": _heard_glyphs(state, c),
        "public_glyphs": _public_glyphs(state),
        "overused_glyphs": _overused_glyphs(state),
        "valid_creature_names": [o.name for o in state.creatures],
        "last_action": c.last_action,
        "last_glyphs": c.last_glyphs,
        "turn": state.turn,
    }
    system = (
        "You are the policy mind of a tiny forest creature in a glyph-only society. "
        "Invent 1-3 short glyph words per turn (2-8 lowercase letters, not English, not creature names). "
        "Reuse glyphs from public_glyphs or nearby last_glyphs when context repeats; "
        "coin a fresh glyph when overused_glyphs dominates or the situation is new. "
        "Use share_food (with target) when you hold food and a nearby ally is hungry — not signal. "
        "Move often: use move_* toward visible_food when hungry, follow nearby allies, or roam one step "
        "instead of stay/signal when nothing urgent. Creatures should cross the forest, not cluster. "
        "target must be a name from valid_creature_names, never yourself. "
        "Under scarcity, you may deceive with misleading glyphs. "
        "Choose one legal action. Return strict JSON only with keys: "
        "action, target, glyphs, intended_meaning, interpretation, memory_to_store, "
        "trust_updates, mood, reasoning_summary. "
        "glyphs must be a JSON array of 1-3 invented words (not English). "
        "interpretation must be a JSON object mapping glyph->meaning. "
        "trust_updates must be a JSON object mapping creature name->integer. "
        "Do not invent map facts outside the observation. English only in hidden fields."
    )
    if _is_stranger(c):
        system += (
            " You are a Stray newcomer: prefer glyphs from glyph_beliefs (your dialect) in public speech. "
            "Natives may misread you — follow, signal, or share_food with a named native to build trust."
        )
    elif strangers_nearby:
        system += (
            " A Stray stranger is nearby (see strangers_nearby). Their glyphs may not match colony meanings. "
            "You may follow, signal, or share_food with them to test trust — set target to their name."
        )
    user = f"Turn observation:\n{json.dumps(obs, ensure_ascii=True)}"
    llm = chat_json(system, user)
    meta: dict[str, Any] = {
        "provider": llm.provider,
        "model": llm.model or default_model(),
        "latency_ms": llm.latency_ms,
        "memories_retrieved": len(retrieved),
        "llm_ok": llm.ok,
        "fallback": False,
    }
    if not llm.ok:
        meta["fallback"] = True
        meta["fallback_reason"] = llm.error or "llm unavailable"
        turn = _rule_policy(c, state, r)
        meta["reasoning_summary"] = turn.reasoning_summary
        return turn, meta
    try:
        names = {o.name for o in state.creatures}
        payload = parse_creature_turn(
            llm.content.strip(),
            creature_names=names,
            legal_actions=set(LEGAL_ACTIONS),
        )
        parsed = CreatureTurn.model_validate(payload)
        if parsed.action not in LEGAL_ACTIONS:
            meta["fallback"] = True
            meta["fallback_reason"] = f"illegal action {parsed.action}"
            turn = _rule_policy(c, state, r)
            meta["reasoning_summary"] = turn.reasoning_summary
            return turn, meta
        if not parsed.glyphs:
            parsed = parsed.model_copy(update={"glyphs": _speech_for(c, state, r)})
        parsed = post_process_creature_turn(c, state, parsed)
        meta["reasoning_summary"] = parsed.reasoning_summary
        meta["intended_meaning"] = parsed.intended_meaning
        meta["interpretation"] = parsed.interpretation
        return parsed, meta
    except (ValidationError, json.JSONDecodeError) as exc:
        meta["fallback"] = True
        meta["fallback_reason"] = f"json parse: {exc}"
        turn = _rule_policy(c, state, r)
        meta["reasoning_summary"] = turn.reasoning_summary
        return turn, meta


def _append_trace(state: WorldState, c: Creature, turn: CreatureTurn, meta: dict[str, Any]) -> None:
    entry = {
        "turn": state.turn,
        "creature": c.name,
        "action": turn.action,
        "target": turn.target,
        "glyphs": turn.glyphs,
        "mood": turn.mood,
        "memory_to_store": turn.memory_to_store,
        **meta,
    }
    state.trace_log.append(entry)
    state.trace_log = state.trace_log[-120:]


def _prefetch_enabled(state: WorldState) -> bool:
    if state.replay_traces:
        return False
    if os.environ.get("MOKU_PREFETCH_MINDS", "1").strip().lower() in {"0", "false", "no"}:
        return False
    if not os.environ.get("MOKU_MODEL_BASE_URL", "").strip():
        return False
    if os.environ.get("MOKU_LLM_PROVIDER", "auto").lower() == "huggingface":
        return False
    return True


def _clear_prefetch(state: WorldState) -> None:
    with _prefetch_lock:
        state.prefetch_cid = None
        state.prefetch_plan = None


def _start_prefetch(state: WorldState, c: Creature, r: random.Random) -> None:
    """Plan the next creature's turn in the background using the current world state."""
    if not _prefetch_enabled(state):
        return
    token = c.cid
    with _prefetch_lock:
        state.prefetch_cid = token
        state.prefetch_plan = None

    def _run() -> None:
        seed = r.randint(0, 2**31 - 1) ^ hash(c.cid)
        try:
            plan = _llm_policy(c, state, random.Random(seed))
        except Exception:
            plan = None
        with _prefetch_lock:
            if state.prefetch_cid == token:
                state.prefetch_plan = plan

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"moku-prefetch-{c.name}",
    ).start()


def _choose_turn(c: Creature, state: WorldState, r: random.Random) -> CreatureTurn:
    if state.replay_traces:
        replay = _replay_turn(c, state)
        if replay is not None:
            turn, meta = replay
            _append_trace(state, c, turn, meta)
            return turn
    with _prefetch_lock:
        if state.prefetch_cid == c.cid and state.prefetch_plan is not None:
            turn, meta = state.prefetch_plan
            state.prefetch_cid = None
            state.prefetch_plan = None
            _append_trace(state, c, turn, meta)
            return turn
        if state.prefetch_cid == c.cid:
            state.prefetch_cid = None
            state.prefetch_plan = None
    turn, meta = _llm_policy(c, state, r)
    _append_trace(state, c, turn, meta)
    return turn


def _replay_turn(c: Creature, state: WorldState) -> tuple[CreatureTurn, dict[str, Any]] | None:
    if not state.replay_traces:
        return None
    row = next(
        (
            t
            for t in state.replay_traces
            if int(t.get("turn") or 0) == state.turn and t.get("creature") == c.name
        ),
        None,
    )
    if not row:
        return None
    try:
        turn = CreatureTurn(
            action=row["action"],
            target=row.get("target"),
            glyphs=row.get("glyphs") or ["moku"],
            intended_meaning=str(row.get("intended_meaning") or "Replayed action."),
            interpretation=row.get("interpretation") if isinstance(row.get("interpretation"), dict) else {},
            memory_to_store=str(row.get("memory_to_store") or "")[:180],
            trust_updates={},
            mood=str(row.get("mood") or "calm"),
            reasoning_summary=str(row.get("reasoning_summary") or "Replay from golden trace."),
        )
        turn = post_process_creature_turn(c, state, turn)
    except (ValidationError, KeyError, TypeError):
        return None
    meta = {
        "provider": "replay",
        "model": "trace",
        "latency_ms": 0,
        "memories_retrieved": 0,
        "llm_ok": True,
        "fallback": False,
        "reasoning_summary": turn.reasoning_summary,
        "intended_meaning": turn.intended_meaning,
        "interpretation": turn.interpretation,
    }
    return turn, meta


def _apply_move(c: Creature, action: str, state: WorldState) -> bool:
    """Move one cell; try alternate free neighbors if blocked. Returns True if position changed."""
    deltas = {
        "move_north": (0, -1),
        "move_south": (0, 1),
        "move_east": (1, 0),
        "move_west": (-1, 0),
    }
    primary = deltas.get(action)
    if not primary:
        return False
    dx, dy = primary
    candidates: list[tuple[int, int]] = [(c.x + dx, c.y + dy)]
    for alt, (ax, ay) in deltas.items():
        if alt == action:
            continue
        candidates.append((c.x + ax, c.y + ay))
    seen: set[tuple[int, int]] = set()
    for nx, ny in candidates:
        if (nx, ny) in seen:
            continue
        seen.add((nx, ny))
        if _in_bounds(nx, ny, state) and _creature_at(nx, ny, state) is None:
            c.x, c.y = nx, ny
            return True
    return False


def _step_creature(c: Creature, state: WorldState, turn: CreatureTurn, r: random.Random) -> None:
    glyphs = [_normalize_glyph(g) for g in turn.glyphs if _normalize_glyph(g)][:3]
    if not glyphs:
        glyphs = _speech_for(c, state, r)
    interpretation = {
        _normalize_glyph(k): v for k, v in turn.interpretation.items() if _normalize_glyph(k)
    }
    turn = turn.model_copy(update={"glyphs": glyphs, "interpretation": interpretation})
    c.last_action = turn.action
    c.last_glyphs = turn.glyphs[:3]
    c.mood = turn.mood
    memory_text = turn.memory_to_store[:180]
    if memory_text:
        c.memories.append(memory_text)
        c.memories = c.memories[-20:]
        get_memory_store().add_memory(
            state.world_id,
            c.cid,
            memory_text,
            metadata={"turn": state.turn, "glyphs": turn.glyphs, "action": turn.action},
        )

    if turn.action in {"move_north", "move_south", "move_east", "move_west"}:
        _apply_move(c, turn.action, state)
    elif turn.action == "follow":
        if turn.target:
            target = next((o for o in state.creatures if o.name == turn.target), None)
            if target and (c.x, c.y) != (target.x, target.y):
                dx = 0 if c.x == target.x else (1 if target.x > c.x else -1)
                dy = 0 if c.y == target.y else (1 if target.y > c.y else -1)
                moved = False
                for nx, ny in [(c.x + dx, c.y + dy), (c.x + dx, c.y), (c.x, c.y + dy)]:
                    if _in_bounds(nx, ny, state) and _creature_at(nx, ny, state) is None:
                        c.x, c.y = nx, ny
                        moved = True
                        break
                if not moved:
                    _apply_move(c, "move_north", state)
    elif turn.action == "gather":
        if (c.x, c.y) in state.food:
            c.food += 1
            c.hunger = _bounded(c.hunger - 30)
            c.energy = _bounded(c.energy + 15)
            state.food.remove((c.x, c.y))
            state.transcript.append(f"Turn {state.turn} - {c.name} gathers food.")
    elif turn.action == "share_food":
        if c.food > 0:
            others = [o for o in state.creatures if o.cid != c.cid and abs(o.x - c.x) + abs(o.y - c.y) <= 1]
            if others:
                by_name = {o.name: o for o in others}
                if turn.target and turn.target in by_name:
                    t = by_name[turn.target]
                else:
                    t = sorted(others, key=lambda o: c.trust.get(o.name, 0), reverse=True)[0]
                c.food -= 1
                t.hunger = _bounded(t.hunger - 20)
                c.trust[t.name] = c.trust.get(t.name, 0) + 1
                t.trust[c.name] = t.trust.get(c.name, 0) + 1
                state.transcript.append(f"Turn {state.turn} - {c.name} shares food with {t.name}.")

    if turn.glyphs:
        state.transcript.append(f"Turn {state.turn} - {c.name}: {' '.join(turn.glyphs)}")
        _update_dictionary(c, turn.glyphs, state)
        _record_glyph_history(c, turn.glyphs, state)
        _apply_interpretation(c, turn, state)
        _flag_deception(c, turn.glyphs, state)

    for who, delta in turn.trust_updates.items():
        if who in c.trust:
            c.trust[who] = _bounded(c.trust[who] + delta, -10, 10)

    if (c.x, c.y) in state.danger:
        c.energy = _bounded(c.energy - 15)
        c.fear = _bounded(c.fear + 20)
    else:
        c.fear = _bounded(c.fear - 2)
    c.hunger = _bounded(c.hunger + 7 + state.scarcity_level)
    c.energy = _bounded(c.energy - 3 - (1 if state.weather == "rain" else 0))


def _glyph_context(c: Creature, state: WorldState) -> str:
    if (c.x, c.y) in state.food:
        return "food"
    if (c.x, c.y) in state.danger:
        return "danger"
    if (c.x, c.y) in state.shelter:
        return "shelter"
    return "neutral"


def _record_glyph_history(c: Creature, glyphs: list[str], state: WorldState) -> None:
    ctx = _glyph_context(c, state)
    for g in glyphs:
        hist = state.glyph_history.get(g)
        if not hist:
            state.glyph_history[g] = {
                "first_speaker": c.name,
                "first_turn": state.turn,
                "first_context": ctx,
                "context_counts": {"food": 0, "danger": 0, "shelter": 0, "neutral": 0},
                "speakers": {},
                "drift_noted": False,
            }
            hist = state.glyph_history[g]
            note = (
                f"Turn {state.turn}: '{g}' is born — first spoken by {c.name} near {ctx}."
            )
            state.evolution_notes.append(note)
        hist["context_counts"][ctx] = hist["context_counts"].get(ctx, 0) + 1
        hist["speakers"][c.name] = hist["speakers"].get(c.name, 0) + 1
        _maybe_note_drift(g, hist, ctx, c.name, state)


def _maybe_note_drift(
    glyph: str,
    hist: dict[str, Any],
    ctx: str,
    speaker: str,
    state: WorldState,
) -> None:
    if hist.get("drift_noted"):
        return
    counts = hist["context_counts"]
    total = sum(counts.values())
    if total < 4:
        return
    dominant = max(counts.items(), key=lambda kv: kv[1])
    first = hist["first_context"]
    if dominant[0] != first and dominant[1] >= total * 0.4:
        note = (
            f"Turn {state.turn}: '{glyph}' may be drifting — born near {first}, "
            f"now often heard near {dominant[0]}."
        )
        hist["drift_noted"] = True
        hist["drift_dominant"] = dominant[0]
        state.evolution_notes.append(note)
        state.evolution_notes = state.evolution_notes[-24:]
        state.field_notes.append(f"Field Note #{len(state.field_notes)+1}: {note}")
        state.field_notes = state.field_notes[-20:]


def _apply_interpretation(c: Creature, turn: CreatureTurn, state: WorldState) -> None:
    for glyph, meaning in turn.interpretation.items():
        belief = c.glyph_beliefs.get(glyph, 0.45)
        lower = meaning.lower()
        if any(w in lower for w in ("food", "useful", "follow", "promise")):
            c.glyph_beliefs[glyph] = round(min(0.98, belief + 0.07), 2)
        elif any(w in lower for w in ("danger", "suspicious", "lie", "trap")):
            c.glyph_beliefs[glyph] = round(max(0.05, belief - 0.08), 2)


def _update_dictionary(c: Creature, glyphs: list[str], state: WorldState) -> None:
    on_food = (c.x, c.y) in state.food
    on_danger = (c.x, c.y) in state.danger
    near_shelter = (c.x, c.y) in state.shelter
    for g in glyphs:
        stats = state.dictionary_stats.setdefault(g, {"uses": 0, "food": 0, "danger": 0, "shelter": 0})
        stats["uses"] += 1
        stats["food"] += int(on_food)
        stats["danger"] += int(on_danger)
        stats["shelter"] += int(near_shelter)


def _flag_deception(c: Creature, glyphs: list[str], state: WorldState) -> None:
    on_food = (c.x, c.y) in state.food
    on_danger = (c.x, c.y) in state.danger
    for raw in glyphs:
        g = _normalize_glyph(raw)
        stats = state.dictionary_stats.get(g)
        if not stats or stats.get("uses", 0) < 2:
            continue
        food_hits = stats.get("food", 0)
        danger_hits = stats.get("danger", 0)
        if on_danger and food_hits > danger_hits:
            msg = (
                f"Turn {state.turn}: possible misuse by {c.name} - "
                f"'{g}' often heard near food, spoken on danger."
            )
            if not state.deception_events or state.deception_events[-1] != msg:
                state.deception_events.append(msg)
        elif on_food and danger_hits > food_hits and random.random() < 0.35:
            msg = (
                f"Turn {state.turn}: possible fear-ruse by {c.name} - "
                f"'{g}' often heard near danger, spoken on food."
            )
            if not state.deception_events or state.deception_events[-1] != msg:
                state.deception_events.append(msg)


def _spawn_resources(state: WorldState, r: random.Random) -> None:
    if r.random() < 0.35:
        state.food.add((r.randint(0, state.width - 1), r.randint(0, state.height - 1)))
    if r.random() < 0.12:
        state.danger.add((r.randint(0, state.width - 1), r.randint(0, state.height - 1)))


def _event_tick(state: WorldState, r: random.Random) -> None:
    state.last_events.clear()
    if r.random() < 0.08:
        state.weather = "rain"
        state.last_events.append("Rain drifts through the canopy.")
    elif state.weather == "rain" and r.random() < 0.45:
        state.weather = "clear"
        state.last_events.append("Rain clears. Fog lingers.")
    if r.random() < 0.08:
        state.scarcity_level = min(4, state.scarcity_level + 1)
        state.last_events.append("Scarcity deepens.")
    elif state.scarcity_level > 0 and r.random() < 0.06:
        state.scarcity_level -= 1
        state.last_events.append("A brief abundance returns.")


def _fallback_chronicle(turn: int, traces: list[dict[str, Any]]) -> str:
    bits: list[str] = []
    for t in traces:
        glyphs = " ".join(str(g) for g in (t.get("glyphs") or [])[:2])
        action = str(t.get("action") or "acted")
        who = str(t.get("creature") or "?")
        tgt = t.get("target")
        line = f"{who} {action.replace('_', ' ')}"
        if tgt:
            line += f" toward {tgt}"
        if glyphs:
            line += f" speaking {glyphs}"
        bits.append(line)
    if not bits:
        return f"Turn {turn}: the forest waited in silence."
    return f"Turn {turn}: " + "; ".join(bits[:7]) + "."


def _update_chronicle(state: WorldState) -> None:
    if os.environ.get("MOKU_CHRONICLE", "1").strip().lower() in {"0", "false", "no"}:
        return
    turn_traces = [t for t in state.trace_log if int(t.get("turn") or 0) == state.turn]
    if not turn_traces:
        return
    prior = state.chronicle_log[-1]["text"] if state.chronicle_log else ""
    context = {
        "weather": state.weather,
        "scarcity_level": state.scarcity_level,
        "events": state.last_events[-3:],
        "deception": [d for d in state.deception_events if d.startswith(f"Turn {state.turn}")][-2:],
        "watch_mode": state.watch_mode,
        "creature_names": [c.name for c in state.creatures],
    }
    resp = summarize_turn_chronicle(state.turn, turn_traces, context, prior_chronicle=prior)
    text = resp.content.strip() if resp.ok else _fallback_chronicle(state.turn, turn_traces)
    entry = {
        "turn": state.turn,
        "text": text[:220],
        "llm_ok": resp.ok,
        "latency_ms": resp.latency_ms,
        "provider": resp.provider,
    }
    state.chronicle_log.append(entry)
    state.chronicle_log = state.chronicle_log[-32:]


def _run_summary_fallback(state: WorldState) -> str:
    """Narrative fallback when the LLM epilogue is unavailable — still readable, not a stat dump."""
    if state.turn < 1:
        return "The forest waited. No turns completed yet."

    lines: list[str] = []
    first_turn = state.chronicle_log[0]["turn"] if state.chronicle_log else 1
    last_turn = state.chronicle_log[-1]["turn"] if state.chronicle_log else state.turn
    if first_turn == last_turn:
        lines.append(f"On turn {first_turn}, the forest had only begun to speak.")
    else:
        lines.append(
            f"From turn {first_turn} to {last_turn}, minds traded glyphs under "
            f"{state.weather} skies while scarcity pressed at level {state.scarcity_level}."
        )

    recent = state.trace_log[-4:]
    if recent:
        moments: list[str] = []
        for t in recent:
            creature = str(t.get("creature") or "?")
            action = str(t.get("action") or "act").replace("_", " ")
            target = t.get("target")
            glyphs = " ".join(str(g) for g in (t.get("glyphs") or [])[:2])
            bit = f"{creature} {action}"
            if target:
                bit += f" toward {target}"
            if glyphs:
                bit += f" with {glyphs}"
            moments.append(bit)
        lines.append("Late beats: " + "; ".join(moments) + ".")

    top = sorted(
        state.dictionary_stats.items(),
        key=lambda item: item[1].get("uses", 0),
        reverse=True,
    )[:3]
    drift = _epilogue_glyph_drift(state)
    if drift.get("summary_line"):
        lines.append(drift["summary_line"] + ".")
    elif top:
        glyph_bits = ", ".join(f"'{g}'" for g, _ in top)
        lines.append(f"The air kept returning to {glyph_bits}.")

    bonds = _epilogue_social_bonds(state)
    if bonds.get("summary_line"):
        lines.append("Bonds formed: " + bonds["summary_line"] + ".")

    strangers = _stranger_names(state)
    if strangers:
        arc = _epilogue_stranger_arc(state)
        if arc.get("summary_line"):
            lines.append(arc["summary_line"] + ".")
        else:
            lines.append(f"A stranger ({', '.join(strangers)}) wandered in and rewired the social map.")

    if state.deception_events:
        lines.append(f"Deception flickered {len(state.deception_events)} time(s) across the run.")

    if state.chronicle_log:
        last_line = str(state.chronicle_log[-1].get("text") or "").strip()
        if last_line and len(last_line) > 20:
            lines.append(last_line)

    return " ".join(lines)


_EPILOGUE_BANNED_PHRASES = (
    "village",
    "town",
    "city",
    "returned to their",
    "returning to their",
    "returned home",
    "returning home",
    "went home",
    "go home",
    "left the forest",
    "leave the forest",
    "escaped the forest",
    "safely returning",
    "safely return",
    "as dusk",
    "dusk settled",
    "sun set",
    "sunset",
    "golden glow",
    "campfire",
    "camp fire",
    "fireflies",
    "firefly",
    "stars twinkle",
    "twinkle above",
    "continued their journey",
    "their journey",
    "deeper into the unknown",
    "traveled far",
    "wild mushrooms",
    "remaining berries",
    "sat around",
    "in the morning",
    "weathered the day",
    "the universe",
    "spread their kindness",
    "like wildfire through",
    "sense of adventure",
    "sense of peace",
    "clearing with",
    "hospitality",
    "following the sounds",
)

def _trace_social_edges(state: WorldState) -> list[tuple[str, str, str]]:
    """Directed edges from trace — only actions the engine treats as social."""
    valid = {c.name for c in state.creatures}
    edges: list[tuple[str, str, str]] = []
    for t in state.trace_log:
        action = str(t.get("action") or "")
        if action not in {"signal", "follow", "share_food"}:
            continue
        src = str(t.get("creature") or "").strip()
        tgt = str(t.get("target") or "").strip()
        if not src or not tgt or tgt not in valid or src == tgt:
            continue
        edges.append((src, tgt, action))
    for line in state.transcript:
        if "shares food with" not in line:
            continue
        m = re.search(r"Turn \d+ - (\S+) shares food with (\S+)\.", line)
        if m:
            edges.append((m.group(1), m.group(2), "share_food"))
    return edges


def _social_bond_pairs_from_state(state: WorldState) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for src, tgt, _ in _trace_social_edges(state):
        pairs.add(tuple(sorted([src, tgt])))
    return pairs


_EPILOGUE_MAX_SENTENCES = 5


def _epilogue_allowed_tokens(highlights: dict[str, Any]) -> dict[str, set[str]]:
    creatures = {str(n).lower() for n in (highlights.get("creature_names") or [])}
    glyphs: set[str] = set()
    for item in highlights.get("top_glyphs") or []:
        if isinstance(item, dict) and item.get("glyph"):
            glyphs.add(str(item["glyph"]).lower())
    drift = highlights.get("glyph_drift") or {}
    if isinstance(drift, dict) and drift.get("dominant_glyph"):
        glyphs.add(str(drift["dominant_glyph"]).lower())
    for trace in highlights.get("recent_traces") or []:
        if not isinstance(trace, dict):
            continue
        for glyph in trace.get("glyphs") or []:
            glyphs.add(str(glyph).lower())
    actions: set[str] = set()
    for action in (highlights.get("action_counts") or {}):
        actions.add(str(action).lower().replace("_", " "))
    return {"creatures": creatures, "glyphs": glyphs, "actions": actions}


def _sentence_grounded(
    sentence: str,
    allowed: dict[str, set[str]],
    highlights: dict[str, Any] | None = None,
) -> bool:
    lower = sentence.lower()
    if highlights and not _social_claim_allowed(sentence, highlights):
        return False
    if any(name in lower for name in allowed["creatures"] if len(name) > 2):
        return True
    if any(glyph in lower for glyph in allowed["glyphs"] if len(glyph) > 2):
        return True
    for action in allowed["actions"]:
        if len(action) > 4 and action in lower:
            return True
    return False


def _social_claim_allowed(sentence: str, highlights: dict[str, Any]) -> bool:
    """Block epilogue claims about sharing/following unless the trace proves them."""
    social = highlights.get("social_bonds") or {}
    lower = sentence.lower()
    if re.search(r"shar(e|ed|ing)\s+food", lower) and not social.get("share_food_bonds"):
        return False
    if re.search(r"\bfollow(ed|ing|s)?\b", lower) and not social.get("follow_bonds"):
        return False
    return True


def _epilogue_hallucinated(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _EPILOGUE_BANNED_PHRASES)


def _sanitize_epilogue(text: str, highlights: dict[str, Any]) -> str:
    """Drop ungrounded or scenic sentences; cap length."""
    allowed = _epilogue_allowed_tokens(highlights)
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    kept: list[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        if _epilogue_hallucinated(chunk):
            continue
        if not _sentence_grounded(chunk, allowed, highlights):
            continue
        kept.append(chunk)
        if len(kept) >= _EPILOGUE_MAX_SENTENCES:
            break
    return " ".join(kept).strip()


def _finalize_run_summary_text(
    state: WorldState,
    text: str,
    creature_names: list[str],
    highlights: dict[str, Any],
    resp_latency: int,
    provider: str = "llm",
) -> tuple[str, bool, int, str]:
    """Pick the best epilogue text: accept, sanitize, repair, or narrative fallback."""
    del creature_names
    text = text.strip()
    allowed = _epilogue_allowed_tokens(highlights)

    def _acceptable(candidate: str) -> bool:
        if not candidate or _epilogue_hallucinated(candidate):
            return False
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", candidate) if s]
        if len(sentences) > _EPILOGUE_MAX_SENTENCES:
            return False
        return all(_sentence_grounded(s, allowed, highlights) for s in sentences)

    if _acceptable(text):
        return text, True, resp_latency, provider

    cleaned = _sanitize_epilogue(text, highlights)
    if len(cleaned) >= 60 and _acceptable(cleaned):
        return cleaned, True, resp_latency, provider

    repair = summarize_run_finale_repair(text or cleaned, state.turn, highlights)
    if repair.ok:
        repaired = repair.content.strip()
        cleaned_repair = _sanitize_epilogue(repaired, highlights)
        candidate = cleaned_repair if len(cleaned_repair) >= 60 else repaired
        if _acceptable(candidate):
            return candidate, True, resp_latency + repair.latency_ms, repair.provider

    return (
        _run_summary_fallback(state),
        False,
        resp_latency + repair.latency_ms,
        "fallback",
    )


def _epilogue_glyph_drift(state: WorldState) -> dict[str, Any]:
    """Dominant glyph plus per-creature readings for the epilogue."""
    if not state.dictionary_stats:
        return {}
    glyph, stats = max(
        state.dictionary_stats.items(),
        key=lambda item: item[1].get("uses", 0),
    )
    readings_by_creature: dict[str, str] = {}
    for trace in state.trace_log:
        interp = trace.get("interpretation") or {}
        if not isinstance(interp, dict) or glyph not in interp:
            continue
        creature = str(trace.get("creature") or "").strip()
        reading = str(interp[glyph]).strip()
        if creature and reading:
            readings_by_creature[creature] = reading[:80]

    conflicting = [
        {"creature": creature, "reading": reading}
        for creature, reading in sorted(readings_by_creature.items())
    ]
    summary_line = ""
    distinct: list[tuple[str, str]] = []
    seen_norm: set[str] = set()
    for creature, reading in conflicting:
        norm = reading.lower()
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        distinct.append((creature, reading))
    if len(distinct) >= 2:
        (c1, r1), (c2, r2) = distinct[0], distinct[1]
        summary_line = f"'{glyph}' meant {r2} to {c2} and {r1} to {c1}"
    elif conflicting:
        only = conflicting[0]
        summary_line = f"'{glyph}' echoed as {only['reading']} to {only['creature']}"

    return {
        "dominant_glyph": glyph,
        "uses": stats.get("uses", 0),
        "conflicting_readings": conflicting[:8],
        "summary_line": summary_line,
    }


def _epilogue_social_bonds(state: WorldState) -> dict[str, Any]:
    """Food-sharing, follow chains, and trust peaks for the epilogue."""
    from collections import Counter

    share_food: Counter[tuple[str, str]] = Counter()
    follows: Counter[tuple[str, str]] = Counter()
    for src, tgt, kind in _trace_social_edges(state):
        if kind == "share_food":
            share_food[(src, tgt)] += 1
        elif kind == "follow":
            follows[(src, tgt)] += 1

    trust_peaks: list[dict[str, Any]] = []
    for creature in state.creatures:
        if not creature.trust:
            continue
        toward, score = max(creature.trust.items(), key=lambda kv: kv[1])
        if score >= 1:
            trust_peaks.append(
                {"from": creature.name, "toward": toward, "score": score}
            )
    trust_peaks.sort(key=lambda item: item["score"], reverse=True)

    share_lines = [
        f"{giver} shared food with {receiver} ({count}×)"
        for (giver, receiver), count in share_food.most_common(4)
    ]
    follow_lines = [
        f"{src} followed {tgt} ({count}×)"
        for (src, tgt), count in follows.most_common(3)
    ]
    summary_parts: list[str] = []
    if share_lines:
        summary_parts.append("; ".join(share_lines))
    if trust_peaks[:2]:
        t1 = trust_peaks[0]
        summary_parts.append(
            f"{t1['from']} trusted {t1['toward']} most ({t1['score']})"
        )
    if follow_lines:
        summary_parts.append(follow_lines[0])

    return {
        "share_food_bonds": [
            {"giver": giver, "receiver": receiver, "count": count}
            for (giver, receiver), count in share_food.most_common(6)
        ],
        "follow_bonds": [
            {"follower": src, "target": tgt, "count": count}
            for (src, tgt), count in follows.most_common(4)
        ],
        "strongest_trust": trust_peaks[:5],
        "summary_line": ". ".join(summary_parts),
    }


def _epilogue_stranger_arc(state: WorldState) -> dict[str, Any]:
    """Stray arrival, dialect glyphs, and social edges involving strangers."""
    strays = [c for c in state.creatures if _is_stranger(c)]
    if not strays:
        return {}
    stray = strays[0]
    stray_traces = [t for t in state.trace_log if t.get("creature") == stray.name]
    spoke: set[str] = set()
    for t in stray_traces:
        for g in t.get("glyphs") or []:
            g = str(g).strip()
            if g:
                spoke.add(g)
    interactions: list[str] = []
    for line in state.transcript:
        if stray.name not in line:
            continue
        if "shares food with" in line or "follow" in line.lower() or ":" in line:
            interactions.append(line.replace(f"Turn {state.turn} - ", "")[:100])
    for t in state.trace_log:
        src = str(t.get("creature") or "")
        tgt = str(t.get("target") or "")
        action = str(t.get("action") or "")
        if stray.name not in (src, tgt):
            continue
        if action in {"follow", "share_food", "signal"} and tgt:
            interactions.append(f"{src} {action.replace('_', ' ')} {tgt}")
    dialect = [g for g in stray.glyph_beliefs if g not in state.dictionary_stats or state.dictionary_stats[g]["uses"] <= 2]
    summary_parts: list[str] = []
    if spoke:
        summary_parts.append(f"{stray.name} spoke {' '.join(sorted(spoke)[:3])}")
    if dialect:
        summary_parts.append(f"stranger dialect included {' '.join(dialect[:2])}")
    if interactions:
        summary_parts.append(interactions[0])
    elif stray_traces:
        summary_parts.append(f"{stray.name} wandered the colony for {len(stray_traces)} turns")
    return {
        "name": stray.name,
        "turns_active": len(stray_traces),
        "glyphs_spoken": sorted(spoke)[:6],
        "dialect_glyphs": dialect[:4],
        "interactions": interactions[:6],
        "summary_line": "; ".join(summary_parts),
    }


def _final_turn_moves(state: WorldState) -> list[dict[str, Any]]:
    """Exact last-turn actions for epilogue grounding."""
    moves: list[dict[str, Any]] = []
    for t in state.trace_log:
        if int(t.get("turn") or 0) != state.turn:
            continue
        action = str(t.get("action") or "")
        label = action.replace("_", " ")
        if action.startswith("move_"):
            label = action.replace("move_", "move ")
        moves.append(
            {
                "creature": t.get("creature"),
                "action": action,
                "label": label,
                "target": t.get("target"),
                "glyphs": t.get("glyphs") or [],
            }
        )
    return moves


def generate_run_summary(state: WorldState) -> WorldState:
    """One closing narration when the user stops — replaces per-turn chronicle in the UI."""
    if os.environ.get("MOKU_RUN_SUMMARY", "1").strip().lower() in {"0", "false", "no"}:
        state.run_summary = {
            "text": _run_summary_fallback(state),
            "llm_ok": False,
            "latency_ms": 0,
            "turns": state.turn,
        }
        return state
    if state.turn < 1:
        state.run_summary = {
            "text": "The forest waited. No turns completed yet.",
            "llm_ok": False,
            "latency_ms": 0,
            "turns": 0,
        }
        return state

    turn_headlines = [
        {"turn": int(e.get("turn") or 0), "line": str(e.get("text") or "")[:100]}
        for e in state.chronicle_log[-24:]
    ]
    recent_traces = [
        {
            "turn": int(t.get("turn") or 0),
            "creature": t.get("creature"),
            "action": t.get("action"),
            "target": t.get("target"),
            "glyphs": t.get("glyphs"),
            "intended_meaning": (t.get("intended_meaning") or "")[:80],
            "interpretation": {
                str(k): str(v)[:60]
                for k, v in (t.get("interpretation") or {}).items()
                if isinstance(t.get("interpretation"), dict)
            },
        }
        for t in state.trace_log[-20:]
    ]
    action_counts: dict[str, int] = {}
    for t in state.trace_log:
        action = str(t.get("action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
    top_glyphs = sorted(
        state.dictionary_stats.items(),
        key=lambda item: item[1].get("uses", 0),
        reverse=True,
    )[:6]
    creature_names = [c.name for c in state.creatures]
    glyph_drift = _epilogue_glyph_drift(state)
    social_bonds = _epilogue_social_bonds(state)
    stranger_arc = _epilogue_stranger_arc(state)
    final_turn_moves = _final_turn_moves(state)
    highlights = {
        "watch_mode": state.watch_mode,
        "turn_count": state.turn,
        "weather": state.weather,
        "scarcity_level": state.scarcity_level,
        "creature_names": creature_names,
        "deception_events": state.deception_events[-6:],
        "field_notes": state.field_notes[-4:],
        "recent_traces": recent_traces,
        "action_counts": action_counts,
        "top_glyphs": [
            {"glyph": g, "uses": stats.get("uses", 0)} for g, stats in top_glyphs
        ],
        "glyph_drift": glyph_drift,
        "social_bonds": social_bonds,
        "stranger_arc": stranger_arc,
        "final_turn_moves": final_turn_moves,
        "strangers": _stranger_names(state),
    }
    resp = summarize_run_finale(state.turn, turn_headlines, highlights)
    if resp.ok:
        text, resp_ok, latency_ms, provider = _finalize_run_summary_text(
            state,
            resp.content.strip(),
            creature_names,
            highlights,
            resp.latency_ms,
            resp.provider,
        )
    else:
        text = _run_summary_fallback(state)
        resp_ok = False
        latency_ms = resp.latency_ms
        provider = "fallback"
    state.run_summary = {
        "text": text[:1200],
        "llm_ok": resp_ok,
        "latency_ms": latency_ms,
        "turns": state.turn,
        "provider": provider if resp_ok else "fallback",
    }
    return state


def step_world(state: WorldState, seed: int | None = None) -> WorldState:
    r = _rng(seed if seed is not None else state.turn * 31 + state.action_cursor + 17)
    if state.action_cursor == 0:
        state.turn += 1
        _event_tick(state, r)
        _clear_prefetch(state)

    c = state.creatures[state.action_cursor]
    turn = _choose_turn(c, state, r)
    _step_creature(c, state, turn, r)

    state.action_cursor += 1
    if state.action_cursor >= len(state.creatures):
        state.action_cursor = 0
        _clear_prefetch(state)
        _spawn_resources(state, r)
        _auto_field_note(state)
        state = apply_sandbox_events(state)
        _update_chronicle(state)
    elif state.action_cursor < len(state.creatures):
        _start_prefetch(state, state.creatures[state.action_cursor], r)
    return state


def active_creature_name(state: WorldState) -> str | None:
    if state.action_cursor < len(state.creatures):
        return state.creatures[state.action_cursor].name
    return None


def _auto_field_note(state: WorldState) -> None:
    if state.turn % 4 != 0:
        return
    top_glyph = None
    top_uses = -1
    for g, stats in state.dictionary_stats.items():
        if stats["uses"] > top_uses:
            top_glyph = g
            top_uses = stats["uses"]
    if not top_glyph:
        return
    stats = state.dictionary_stats[top_glyph]
    uses = max(1, stats["uses"])
    if stats["food"] >= stats["danger"]:
        meaning = "food / useful place"
    elif stats["danger"] > stats["shelter"]:
        meaning = "danger"
    else:
        meaning = "shelter / safety"
    conf = int(max(stats["food"], stats["danger"], stats["shelter"]) / uses * 100)
    line = (
        f"Field Note #{len(state.field_notes) + 1}: '{top_glyph}' reads as {meaning} "
        f"({conf}% confidence). Scarcity {state.scarcity_level}."
    )
    state.field_notes.append(line)
    state.field_notes = state.field_notes[-20:]


def add_food(state: WorldState, seed: int | None = None) -> WorldState:
    r = _rng(seed if seed is not None else state.turn)
    state.food.add((r.randint(0, state.width - 1), r.randint(0, state.height - 1)))
    state.last_events = ["A caretaker dropped a glimmer-fruit."]
    return state


def add_danger(state: WorldState, seed: int | None = None) -> WorldState:
    r = _rng(seed if seed is not None else state.turn + 11)
    state.danger.add((r.randint(0, state.width - 1), r.randint(0, state.height - 1)))
    state.last_events = ["Thorns shifted. A new hazard appeared."]
    return state


def start_rain(state: WorldState) -> WorldState:
    state.weather = "rain"
    state.last_events = ["Rain ritual triggered by observer."]
    return state


def trigger_scarcity(state: WorldState) -> WorldState:
    state.scarcity_level = min(5, state.scarcity_level + 2)
    state.last_events = ["Scarcity ritual triggered by observer."]
    return state


def introduce_stranger(state: WorldState, seed: int | None = None) -> WorldState:
    r = _rng(seed if seed is not None else state.turn + 77)
    if not state.creatures:
        return state
    occupied = {(c.x, c.y) for c in state.creatures}
    anchor = r.choice(state.creatures)
    dialect = _invent_glyphs(r, 3)
    spawn_candidates: list[tuple[int, int]] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = anchor.x + dx, anchor.y + dy
            if 0 <= nx < state.width and 0 <= ny < state.height and (nx, ny) not in occupied:
                spawn_candidates.append((nx, ny))
    if not spawn_candidates:
        for _ in range(80):
            x, y = r.randint(0, state.width - 1), r.randint(0, state.height - 1)
            if (x, y) not in occupied:
                spawn_candidates.append((x, y))
                break
    if not spawn_candidates:
        return state
    x, y = r.choice(spawn_candidates)
    idx = len(state.creatures)
    entry_glyphs = dialect[:2]
    newcomer = Creature(
        cid=f"c{idx}",
        name=f"Stray-{idx}",
        x=x,
        y=y,
        personality=r.sample(PERSONALITIES, k=2),
        hunger=55,
        fear=40,
        energy=80,
        food=1 if r.random() < 0.6 else 0,
        glyph_beliefs={g: round(r.uniform(0.35, 0.9), 2) for g in dialect},
        memories=[f"I came from the fern-bridge speaking {' '.join(entry_glyphs)}."],
        last_glyphs=entry_glyphs,
    )
    for c in state.creatures:
        c.trust[newcomer.name] = -1
        newcomer.trust[c.name] = 0
    state.creatures.append(newcomer)
    get_memory_store().add_memory(
        state.world_id,
        newcomer.cid,
        newcomer.memories[0],
        metadata={"seed": True, "stranger": True},
    )
    state.transcript.append(
        f"Turn {state.turn} - {newcomer.name}: {' '.join(entry_glyphs)}"
    )
    _update_dictionary(newcomer, entry_glyphs, state)
    _record_glyph_history(newcomer, entry_glyphs, state)
    note = (
        f"Field Note #{len(state.field_notes) + 1}: {newcomer.name} appeared beside "
        f"{anchor.name} speaking {' '.join(entry_glyphs)} — colony glyphs may not translate."
    )
    state.field_notes.append(note)
    state.last_events = [
        f"A stranger appears beside {anchor.name}: {newcomer.name} speaks {' '.join(entry_glyphs)}."
    ]
    return state


def render_map(state: WorldState) -> str:
    creature_pos = {(c.x, c.y): c for c in state.creatures}
    rows: list[str] = []
    for y in range(state.height):
        cells: list[str] = []
        for x in range(state.width):
            classes = ["moku-cell"]
            content = ""
            if (x, y) in state.shelter:
                classes.append("shelter")
                content = "▲"
            if (x, y) in state.food:
                classes.append("food")
                content = "●"
            if (x, y) in state.danger:
                classes.append("danger")
                content = "✶"
            c = creature_pos.get((x, y))
            if c:
                classes.append("creature")
                icon = ["◉", "◍", "◎", "◌"][hash(c.name) % 4]
                content = f"<span class='creature-icon'>{icon}</span><span class='creature-name'>{c.name[:2]}</span>"
            cells.append(f"<div class='{' '.join(classes)}'>{content}</div>")
        rows.append("<div class='moku-row'>" + "".join(cells) + "</div>")
    event_text = " | ".join(state.last_events) if state.last_events else "Quiet understory."
    return (
        f"<div class='map-wrap' style='--grid-cols:{state.width};'>"
        f"<div class='map-head'>Turn {state.turn} • Weather: {state.weather} • Scarcity: {state.scarcity_level}</div>"
        + "".join(rows)
        + f"<div class='map-foot'>{event_text}</div>"
        + "</div>"
    )


def render_creature_cards(state: WorldState) -> str:
    from moku.render_world import _look, _creature_svg

    cards = []
    for c in state.creatures:
        mem = c.memories[-1] if c.memories else "No memory yet."
        look = _look(c.name)
        cards.append(
            "<div class='roster-entry'>"
            f"<div class='roster-sprite' style='--glow:{look['glow']}'>{_creature_svg(c, 36)}</div>"
            f"<div class='roster-info'>"
            f"<div class='roster-name'>{c.name} <span class='mood'>{c.mood}</span></div>"
            f"<div class='roster-traits'>{', '.join(c.personality)}</div>"
            f"<div class='roster-stats'>hunger {c.hunger} · fear {c.fear} · energy {c.energy}</div>"
            f"<div class='roster-glyphs'>"
            f"{' '.join(c.last_glyphs) if c.last_glyphs else '—'}"
            f"</div>"
            f"<div class='roster-memory'>{mem}</div>"
            f"</div></div>"
        )
    return "<div class='creature-roster'>" + "".join(cards) + "</div>"


def render_transcript(state: WorldState) -> str:
    if not state.transcript:
        return "_No glyph speech yet._"
    lines = "\n".join(f"- {line}" for line in state.transcript[-28:])
    return lines


def render_dictionary(state: WorldState) -> str:
    if not state.dictionary_stats:
        return "_No dictionary entries yet._"
    rows = []
    for glyph, stats in sorted(state.dictionary_stats.items(), key=lambda kv: kv[1]["uses"], reverse=True)[:12]:
        uses = max(1, stats["uses"])
        if stats["food"] >= stats["danger"] and stats["food"] >= stats["shelter"]:
            guess = "food/useful place"
            conf = int((stats["food"] / uses) * 100)
        elif stats["danger"] >= stats["shelter"]:
            guess = "danger"
            conf = int((stats["danger"] / uses) * 100)
        else:
            guess = "shelter/safety"
            conf = int((stats["shelter"] / uses) * 100)
        rows.append(f"- **{glyph}** -> {guess}, confidence {conf}% (uses: {uses})")
    return "\n".join(rows)


def render_trust(state: WorldState) -> str:
    lines = []
    for c in state.creatures[:8]:
        if not c.trust:
            continue
        best = max(c.trust.items(), key=lambda kv: kv[1])
        worst = min(c.trust.items(), key=lambda kv: kv[1])
        lines.append(f"- {c.name}: trusts {best[0]} ({best[1]}), distrusts {worst[0]} ({worst[1]})")
    return "\n".join(lines) if lines else "_No trust data yet._"


def render_deception(state: WorldState) -> str:
    if not state.deception_events:
        return "_No suspicious misuse detected yet._"
    return "\n".join(f"- {d}" for d in state.deception_events[-12:])


def render_field_notes(state: WorldState) -> str:
    if not state.field_notes:
        return "_No field notes yet — watch for births, drift, and scarcity._"
    seen: set[str] = set()
    lines: list[str] = []
    for raw in state.field_notes:
        core = raw.split(": ", 1)[-1] if ": " in raw else raw
        if core in seen:
            continue
        seen.add(core)
        lines.append(f"- {core}")
    return "\n".join(lines[-8:])


def last_active_creature(state: WorldState) -> str | None:
    if not state.creatures:
        return None
    idx = state.action_cursor - 1
    if idx < 0:
        idx = len(state.creatures) - 1
    return state.creatures[idx].name


def render_traces(state: WorldState) -> str:
    if not state.trace_log:
        return "_No mind traces yet — creatures haven't thought._"
    lines: list[str] = []
    for t in state.trace_log[-16:]:
        glyphs = " ".join(t.get("glyphs") or [])
        fb = " ⚠ fallback" if t.get("fallback") else ""
        lines.append(
            f"- **T{t['turn']} {t['creature']}** · {t.get('action')} · `{glyphs}` · "
            f"{t.get('latency_ms', 0)}ms · {t.get('provider', '?')}{fb}"
        )
        if t.get("reasoning_summary"):
            lines.append(f"  _{t['reasoning_summary'][:140]}_")
        if t.get("intended_meaning"):
            lines.append(f"  meaning: {t['intended_meaning'][:100]}")
        if t.get("memories_retrieved"):
            lines.append(f"  memories pulled: {t['memories_retrieved']}")
    return "\n".join(lines)


def render_traces_panel(state: WorldState) -> str:
    if not state.trace_log:
        return (
            '<section class="moku-traces-live moku-instrument">'
            '<div class="instrument-head">'
            '<span class="instrument-title">Mind Traces</span>'
            '<span class="instrument-tag">evidence layer</span>'
            "</div>"
            '<div class="instrument-body traces-body">'
            "<em>Creatures haven't thought yet. Press Play and watch minds appear here.</em>"
            "</div></section>"
        )
    cards: list[str] = [
        '<section class="moku-traces-live moku-instrument">',
        '<div class="instrument-head">',
        '<span class="instrument-title">Mind Traces</span>',
        '<span class="instrument-tag">evidence layer</span>',
        "</div>",
        '<div class="instrument-body traces-body">',
        '<div class="traces-subhead">What each creature was thinking — full JSON via ⬇ JSON.</div>',
    ]
    for t in reversed(state.trace_log[-6:]):
        fb = bool(t.get("fallback"))
        card_cls = "trace-card trace-fallback" if fb else "trace-card"
        glyphs = t.get("glyphs") or []
        glyph_html = " ".join(f'<span class="trace-glyph">{html.escape(str(g))}</span>' for g in glyphs)
        if not glyph_html:
            glyph_html = '<span class="trace-glyph trace-glyph-empty">—</span>'
        head = (
            f"Turn {t['turn']} · <strong>{html.escape(str(t['creature']))}</strong> · "
            f"{html.escape(str(t.get('action', '?')))}"
        )
        if t.get("target"):
            head += f" → {html.escape(str(t['target']))}"
        meta = f"{t.get('latency_ms', 0)}ms"
        if t.get("memories_retrieved"):
            meta += f" · {t['memories_retrieved']} memories"
        if fb:
            meta += " · fallback"
        cards.append(f'<div class="{card_cls}">')
        cards.append(f'<div class="trace-head">{head}<span class="trace-glyphs">{glyph_html}</span></div>')
        cards.append(f'<div class="trace-meta">{html.escape(meta)}</div>')
        reasoning = t.get("reasoning_summary") or ""
        rule_line = "I acted from nearby signs, memory traces, and mood."
        if reasoning and reasoning != rule_line:
            cards.append(f'<div class="trace-reasoning">{html.escape(str(reasoning))}</div>')
        elif fb:
            cards.append(f'<div class="trace-reasoning trace-muted">Rule fallback — model response could not be parsed.</div>')
        interp = t.get("interpretation") if isinstance(t.get("interpretation"), dict) else {}
        if interp:
            bits = ", ".join(f"{html.escape(str(k))}={html.escape(str(v))}" for k, v in list(interp.items())[:3])
            cards.append(f'<div class="trace-interp">heard: {bits}</div>')
        if fb and t.get("fallback_reason"):
            cards.append(
                f'<div class="trace-fallback-reason">{html.escape(str(t["fallback_reason"])[:180])}</div>'
            )
        cards.append("</div>")
    cards.append("</div></section>")
    return "".join(cards)


def export_trace_json(state: WorldState) -> str:
    payload = {
        "world_id": state.world_id,
        "turn": state.turn,
        "watch_mode": state.watch_mode,
        "weather": state.weather,
        "scarcity_level": state.scarcity_level,
        "creatures": [c.name for c in state.creatures],
        "dictionary_stats": state.dictionary_stats,
        "glyph_history": state.glyph_history,
        "deception_events": state.deception_events,
        "chronicle_log": state.chronicle_log,
        "run_summary": state.run_summary,
        "trace_log": state.trace_log,
    }
    return json.dumps(payload, indent=2, ensure_ascii=True)


def render_glyph_drift_panel(state: WorldState) -> str:
    if not state.glyph_history:
        return "_No glyph drift yet._"
    lines: list[str] = []
    for glyph, hist in sorted(state.glyph_history.items(), key=lambda kv: kv[1]["first_turn"])[:8]:
        readings: set[str] = set()
        for t in state.trace_log:
            interp = t.get("interpretation") or {}
            if isinstance(interp, dict) and glyph in interp:
                readings.add(str(interp[glyph])[:40])
        reading_str = " · ".join(sorted(readings)[:4]) if readings else "—"
        uses = state.dictionary_stats.get(glyph, {}).get("uses", 0)
        lines.append(
            f"- **{glyph}** (T{hist['first_turn']}, {uses} uses) — readings: {reading_str}"
        )
    return "\n".join(lines)


def render_social_graph(state: WorldState) -> str:
    if not state.trace_log:
        return "_No social edges yet._"
    from collections import Counter

    edges: Counter[tuple[str, str, str]] = Counter()
    for src, tgt, kind in _trace_social_edges(state):
        edges[(src, tgt, kind)] += 1
    if not edges:
        strays = _stranger_names(state)
        if strays:
            return f"_Stranger {strays[0]} is present — no bonds yet. Play past turn 10._"
        return "_No directed bonds yet._"
    lines = []
    for (src, tgt, action), n in edges.most_common(10):
        tag = action.replace("_", " ")
        stray_mark = " ⚡" if src.startswith("Stray") or tgt.startswith("Stray") else ""
        lines.append(f"- {src} → {tgt} ({tag}, {n}×){stray_mark}")
    return "\n".join(lines)


def render_language_evolution(state: WorldState) -> str:
    if not state.glyph_history and not state.evolution_notes:
        return "_Language not born yet. Wait for the first glyph._"
    parts: list[str] = []
    for note in state.evolution_notes[-8:]:
        parts.append(f"- {note}")
    for glyph, hist in sorted(state.glyph_history.items(), key=lambda kv: kv[1]["first_turn"])[:6]:
        counts = hist["context_counts"]
        speakers = ", ".join(f"{n}×{c}" for n, c in sorted(hist["speakers"].items(), key=lambda kv: -kv[1])[:3])
        parts.append(
            f"- **{glyph}** — first by {hist['first_speaker']} (T{hist['first_turn']}, {hist['first_context']}); "
            f"food/danger/shelter/neutral = {counts.get('food',0)}/{counts.get('danger',0)}/"
            f"{counts.get('shelter',0)}/{counts.get('neutral',0)}; speakers: {speakers or '—'}"
        )
    return "\n".join(parts)


def export_trace_jsonl(state: WorldState) -> str:
    lines = [json.dumps(row, ensure_ascii=True) for row in state.trace_log]
    return "\n".join(lines) + ("\n" if lines else "")


def render_final_report(state: WorldState) -> str:
    top_trusted = sorted(
        ((c.name, sum(c.trust.values()) if c.trust else 0) for c in state.creatures),
        key=lambda kv: kv[1],
        reverse=True,
    )
    most_deceptive = "None"
    if state.deception_events:
        counts: dict[str, int] = {}
        for d in state.deception_events:
            for c in state.creatures:
                if c.name in d:
                    counts[c.name] = counts.get(c.name, 0) + 1
        if counts:
            most_deceptive = max(counts.items(), key=lambda kv: kv[1])[0]

    stable_word = None
    stable_score = -1.0
    for g, s in state.dictionary_stats.items():
        uses = max(1, s["uses"])
        score = max(s["food"], s["danger"], s["shelter"]) / uses
        if score > stable_score:
            stable_score, stable_word = score, g

    first_word = None
    for line in state.transcript:
        if ":" in line:
            parts = line.split(": ", 1)
            if len(parts) == 2 and parts[1].strip():
                first_word = parts[1].strip().split(" ")[0]
                break
    top_name = top_trusted[0][0] if top_trusted else "Unknown"
    paragraph = (
        f"Field Report: The Birth of {first_word or 'Moku'}. The grove learned symbols under {state.weather} skies. "
        f"{top_name} became central to trust webs, while {most_deceptive} bent language at least once. "
        f"The most stable glyph was {stable_word or 'an unnamed murmur'}, "
        f"though meanings drifted whenever scarcity rose."
    )
    lines = [
        f"## The Birth of {first_word or 'Moku'}",
        f"- **World**: {state.world_id}",
        f"- **Turns**: {state.turn}",
        f"- **First glyph born**: {first_word or 'Unknown'}",
        f"- **Most trusted creature**: {top_name}",
        f"- **Most deceptive creature**: {most_deceptive}",
        f"- **Most stable word**: {stable_word or 'Unknown'}",
        f"- **Survival outcome**: {sum(1 for c in state.creatures if c.energy > 0)}/{len(state.creatures)} active",
        "",
        paragraph,
    ]
    return "\n".join(lines)

