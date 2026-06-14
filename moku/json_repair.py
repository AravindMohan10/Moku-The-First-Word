"""Coerce small-model JSON into CreatureTurn shape."""

from __future__ import annotations

import json
import re
from typing import Any


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = [f"{k}: {v}" for k, v in value.items()]
        return "; ".join(parts)[:240]
    if isinstance(value, list):
        return " ".join(str(v) for v in value)[:240]
    return str(value)[:240]


def _as_glyph_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [g for g in value.replace(",", " ").split() if g][:3]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif item is not None:
                out.append(str(item))
        return out[:3]
    return []


def _as_interpretation(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): _as_text(v) for k, v in value.items() if k}


def _as_trust(value: Any) -> dict[str, int]:
    if isinstance(value, list):
        return {}
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in value.items():
        if isinstance(v, (int, float)):
            out[str(k)] = int(v)
    return out


def _as_target(value: Any, creature_names: set[str] | None) -> str | None:
    names = creature_names or set()
    if value is None or value == "":
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned in names:
            return cleaned
        # Keep only plausible creature names; drop coords/placeholders.
        if cleaned.replace("_", "").isalpha() and cleaned[0].isupper():
            return cleaned if cleaned in names else None
        return None
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item in names:
                return item
        return None
    return None


def _match_truncated_action(partial: str, legal: set[str]) -> str | None:
    token = partial.strip().lower().replace("-", "_").replace(" ", "_")
    if len(token) < 3:
        return None
    matches = sorted(a for a in legal if a.startswith(token))
    if len(matches) == 1:
        return matches[0]
    return None


def _normalize_action(value: Any, legal_actions: set[str] | None) -> str | None:
    if not isinstance(value, str):
        return None
    action = value.strip().lower().replace("-", "_").replace(" ", "_")
    legal = legal_actions or set()
    if action in legal:
        return action
    aliases = {
        "north": "move_north",
        "south": "move_south",
        "east": "move_east",
        "west": "move_west",
        "move": "stay",
        "speak": "signal",
        "talk": "signal",
        "warn": "signal",
        "scatter": "stay",
        "flee": "hide",
        "run": "move_north",
        "share": "share_food",
        "feed": "share_food",
        "sharefood": "share_food",
        "shar": "share_food",
        "share_f": "share_food",
        "sharefo": "share_food",
        "sharefoood": "share_food",
        "sig": "signal",
        "sign": "signal",
        "signa": "signal",
        "fol": "follow",
        "foll": "follow",
        "follo": "follow",
        "gat": "gather",
        "gath": "gather",
        "gathere": "gather",
        "hid": "hide",
        "move_towards": "stay",
        "move_toward": "stay",
        "move_to": "stay",
        "go_towards": "stay",
        "walk_towards": "stay",
        "approach": "follow",
    }
    if action in aliases and aliases[action] in legal:
        return aliases[action]
    for direction in ("north", "south", "east", "west"):
        if direction in action:
            candidate = f"move_{direction}"
            if candidate in legal:
                return candidate
    truncated = _match_truncated_action(action, legal)
    if truncated:
        return truncated
    return action if action in legal else None


def repair_creature_payload(
    raw: dict[str, Any],
    *,
    creature_names: set[str] | None = None,
    legal_actions: set[str] | None = None,
) -> dict[str, Any]:
    out = dict(raw)

    action = _normalize_action(out.get("action"), legal_actions)
    if action:
        out["action"] = action

    glyphs = _as_glyph_list(out.get("glyphs"))
    if glyphs:
        out["glyphs"] = glyphs

    intended = out.get("intended_meaning")
    if isinstance(intended, dict):
        extra_interp = _as_interpretation(intended)
        base_interp = _as_interpretation(out.get("interpretation"))
        base_interp.update(extra_interp)
        out["interpretation"] = base_interp
        out["intended_meaning"] = _as_text(intended)
    else:
        out["intended_meaning"] = _as_text(intended)

    out["interpretation"] = _as_interpretation(out.get("interpretation"))
    out["trust_updates"] = _as_trust(out.get("trust_updates"))
    out["memory_to_store"] = _as_text(out.get("memory_to_store"))
    out["mood"] = _as_text(out.get("mood")) or "calm"
    out["reasoning_summary"] = _as_text(out.get("reasoning_summary"))
    out["target"] = _as_target(out.get("target"), creature_names)

    return out


def _extract_json_object(content: str) -> str:
    text = content.strip()
    if "```" in text:
        for part in text.split("```"):
            chunk = part.strip()
            if chunk.startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                return chunk
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _repair_truncated_action_field(blob: str, legal_actions: set[str] | None) -> str:
    legal = legal_actions or set()

    def _complete_action(match: re.Match[str]) -> str:
        raw = match.group(1)
        fixed = _normalize_action(raw, legal) or _normalize_action(f"{raw}e", legal)
        if not fixed:
            return match.group(0)
        return f'"action": "{fixed}"'

    return re.sub(
        r'"action"\s*:\s*"([^"]*)',
        _complete_action,
        blob,
        count=1,
        flags=re.IGNORECASE,
    )


def _extract_creature_fields(
    text: str,
    *,
    legal_actions: set[str] | None = None,
) -> dict[str, Any] | None:
    blob = _extract_json_object(text)
    action_m = re.search(r'"action"\s*:\s*"([^"]*)', blob, re.IGNORECASE)
    if not action_m:
        return None
    action = _normalize_action(action_m.group(1), legal_actions)
    if not action:
        return None
    out: dict[str, Any] = {"action": action}
    target_m = re.search(r'"target"\s*:\s*(null|"([^"]*)")', blob, re.IGNORECASE)
    if target_m:
        out["target"] = None if target_m.group(1) == "null" else target_m.group(2)
    glyphs_m = re.search(r'"glyphs"\s*:\s*\[(.*?)\]', blob, re.DOTALL | re.IGNORECASE)
    if glyphs_m:
        glyphs = re.findall(r'"([^"]+)"', glyphs_m.group(1))
        if glyphs:
            out["glyphs"] = glyphs[:3]
    for key in ("intended_meaning", "memory_to_store", "mood", "reasoning_summary"):
        field_m = re.search(rf'"{key}"\s*:\s*"([^"]*)', blob, re.IGNORECASE)
        if field_m:
            out[key] = field_m.group(1)
    interp_m = re.search(r'"interpretation"\s*:\s*\{(.*?)\}', blob, re.DOTALL | re.IGNORECASE)
    if interp_m:
        interp = {
            k: v
            for k, v in re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', interp_m.group(1))
        }
        if interp:
            out["interpretation"] = interp
    trust_m = re.search(r'"trust_updates"\s*:\s*\{(.*?)\}', blob, re.DOTALL | re.IGNORECASE)
    if trust_m:
        trust = {
            k: int(v)
            for k, v in re.findall(r'"([^"]+)"\s*:\s*(-?\d+)', trust_m.group(1))
        }
        if trust:
            out["trust_updates"] = trust
    return out


def _loads_lenient(
    text: str,
    *,
    legal_actions: set[str] | None = None,
) -> dict[str, Any]:
    import ast

    blob = _extract_json_object(text)
    attempts = [
        blob,
        _repair_truncated_action_field(blob, legal_actions),
        re.sub(r",\s*}", "}", blob),
        re.sub(r",\s*]", "]", blob),
        re.sub(r",\s*}", "}", _repair_truncated_action_field(blob, legal_actions)),
    ]
    seen: set[str] = set()
    for candidate in attempts:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        try:
            parsed = ast.literal_eval(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (SyntaxError, ValueError):
            pass
    extracted = _extract_creature_fields(text, legal_actions=legal_actions)
    if extracted:
        return extracted
    raise json.JSONDecodeError("Could not parse creature JSON", blob, 0)


def parse_creature_turn(
    content: str,
    *,
    creature_names: set[str] | None = None,
    legal_actions: set[str] | None = None,
) -> dict[str, Any]:
    raw = _loads_lenient(content, legal_actions=legal_actions)
    return repair_creature_payload(raw, creature_names=creature_names, legal_actions=legal_actions)
