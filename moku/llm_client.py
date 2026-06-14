"""LLM inference — Hugging Face Inference API first, local OpenAI-compatible fallback."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    latency_ms: int
    ok: bool
    error: str | None = None


def _hf_token() -> str:
    for key in ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN", "MOKU_HF_TOKEN"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return ""


# OpenBMB has no exact 3B checkpoint — MiniCPM3-4B is the quality pick (≤4B, Tiny Titan eligible).
OPENBMB_DEFAULT_MODEL = "openbmb/MiniCPM3-4B"


def default_model() -> str:
    return os.environ.get(
        "MOKU_HF_MODEL",
        os.environ.get("MOKU_MODEL_NAME", OPENBMB_DEFAULT_MODEL),
    ).strip()


def _model_fallbacks() -> list[str]:
    raw = os.environ.get(
        "MOKU_HF_MODEL_FALLBACKS",
        "Qwen/Qwen2.5-Coder-3B-Instruct,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
    )
    seen: set[str] = set()
    out: list[str] = []
    primary = default_model()
    for m in [primary, *raw.split(",")]:
        m = m.strip()
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def provider_label() -> str:
    base = os.environ.get("MOKU_MODEL_BASE_URL", "").strip()
    prefer = os.environ.get("MOKU_LLM_PROVIDER", "auto").lower()
    if base and prefer in ("auto", "local"):
        return f"local/{default_model()}"
    if _hf_token():
        return f"huggingface/{default_model()}"
    if base:
        return f"local/{default_model()}"
    return "unconfigured"


def _local_chat_url(base_url: str) -> str:
    """OpenAI-compatible chat URL; base may be .../v1 or host root."""
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def warmup_local_backend() -> None:
    """Background ping so Modal vLLM compiles before the first creature turn."""
    base_url = os.environ.get("MOKU_MODEL_BASE_URL", "").strip()
    prefer = os.environ.get("MOKU_LLM_PROVIDER", "auto").lower()
    if not base_url or prefer == "huggingface":
        return

    def _run() -> None:
        try:
            _chat_local('Reply JSON only: {"ok":true}', "warmup", default_model(), max_tokens=8)
        except Exception:
            pass

    import threading

    threading.Thread(target=_run, daemon=True, name="moku-llm-warmup").start()


def _extract_json(text: str) -> str:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            chunk = part.strip()
            if chunk.startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                return chunk
    match = _JSON_BLOCK.search(text)
    return match.group(0) if match else text


def _chat_hf(
    system: str,
    user: str,
    model: str,
    *,
    max_tokens: int | None = None,
    raw: bool = False,
    temperature: float | None = None,
) -> LLMResponse:
    from huggingface_hub import InferenceClient

    token = _hf_token()
    client = InferenceClient(api_key=token)
    started = time.perf_counter()
    tok = max_tokens or int(os.environ.get("MOKU_MAX_TOKENS", "420"))
    temp = temperature if temperature is not None else float(os.environ.get("MOKU_TEMPERATURE", "0.65"))
    try:
        out = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=tok,
            temperature=temp,
        )
        content = out.choices[0].message.content or ""
        if not raw:
            content = _extract_json(content)
        else:
            content = content.strip()
        latency = int((time.perf_counter() - started) * 1000)
        return LLMResponse(
            content=content,
            provider="huggingface",
            model=model,
            latency_ms=latency,
            ok=bool(content),
        )
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return LLMResponse(
            content="",
            provider="huggingface",
            model=model,
            latency_ms=latency,
            ok=False,
            error=str(exc),
        )


def _chat_local(
    system: str,
    user: str,
    model: str,
    *,
    max_tokens: int | None = None,
    raw: bool = False,
    temperature: float | None = None,
) -> LLMResponse:
    base_url = os.environ.get("MOKU_MODEL_BASE_URL", "").strip()
    api_key = os.environ.get("MOKU_MODEL_API_KEY", "local")
    if not base_url:
        return LLMResponse("", "local", model, 0, False, "no local base url")
    temp = temperature if temperature is not None else float(os.environ.get("MOKU_TEMPERATURE", "0.65"))
    body: dict[str, Any] = {
        "model": model,
        "temperature": temp,
        "max_tokens": max_tokens or int(os.environ.get("MOKU_MAX_TOKENS", "420")),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if not raw:
        local_json = os.environ.get(
            "MOKU_LOCAL_JSON_MODE",
            os.environ.get("MOKU_JSON_MODE", "0"),
        )
        if local_json == "1":
            body["response_format"] = {"type": "json_object"}
    started = time.perf_counter()
    try:
        res = requests.post(
            _local_chat_url(base_url),
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=int(os.environ.get("MOKU_LLM_TIMEOUT", "25")),
        )
        res.raise_for_status()
        payload = res.json()
        content = payload["choices"][0]["message"]["content"]
        if not raw:
            content = _extract_json(content)
        else:
            content = (content or "").strip()
        latency = int((time.perf_counter() - started) * 1000)
        return LLMResponse(
            content=content,
            provider="local",
            model=model,
            latency_ms=latency,
            ok=bool(content),
        )
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return LLMResponse(
            content="",
            provider="local",
            model=model,
            latency_ms=latency,
            ok=False,
            error=str(exc),
        )


def chat_json(system: str, user: str) -> LLMResponse:
    prefer = os.environ.get("MOKU_LLM_PROVIDER", "auto").lower()
    base_url = os.environ.get("MOKU_MODEL_BASE_URL", "").strip()

    if prefer == "local" or (prefer == "auto" and base_url):
        local = _chat_local(system, user, default_model())
        if local.ok:
            return local

    if prefer == "local":
        return LLMResponse("", "local", default_model(), 0, False, "no local base url")

    if prefer == "huggingface" or _hf_token():
        last: LLMResponse | None = None
        for model in _model_fallbacks():
            resp = _chat_hf(system, user, model)
            if resp.ok:
                return resp
            last = resp
            if resp.error and "model_not_supported" not in resp.error:
                break
        if last and base_url:
            local = _chat_local(system, user, default_model())
            if local.ok:
                return local
        if last:
            return last

    if base_url:
        local = _chat_local(system, user, default_model())
        if local.ok:
            return local

    return LLMResponse("", "none", default_model(), 0, False, "configure HF_TOKEN or MOKU_MODEL_BASE_URL")


def _route_prose(
    system: str,
    user: str,
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> LLMResponse:
    prefer = os.environ.get("MOKU_LLM_PROVIDER", "auto").lower()
    base_url = os.environ.get("MOKU_MODEL_BASE_URL", "").strip()
    temp = temperature if temperature is not None else float(os.environ.get("MOKU_CHRONICLE_TEMPERATURE", "0.45"))
    tok = max_tokens or int(os.environ.get("MOKU_CHRONICLE_MAX_TOKENS", "55"))

    if prefer == "local" or (prefer == "auto" and base_url):
        local = _chat_local(system, user, default_model(), max_tokens=tok, raw=True, temperature=temp)
        if local.ok:
            return local

    if prefer == "local":
        return LLMResponse("", "local", default_model(), 0, False, "no local base url")

    if prefer == "huggingface" or _hf_token():
        last: LLMResponse | None = None
        for model in _model_fallbacks():
            resp = _chat_hf(system, user, model, max_tokens=tok, raw=True, temperature=temp)
            if resp.ok:
                return resp
            last = resp
            if resp.error and "model_not_supported" not in (resp.error or ""):
                break
        if last and base_url:
            local = _chat_local(system, user, default_model(), max_tokens=tok, raw=True, temperature=temp)
            if local.ok:
                return local
        if last:
            return last

    if base_url:
        local = _chat_local(system, user, default_model(), max_tokens=tok, raw=True, temperature=temp)
        if local.ok:
            return local

    return LLMResponse("", "none", default_model(), 0, False, "configure HF_TOKEN or MOKU_MODEL_BASE_URL")


def summarize_turn_chronicle(
    turn: int,
    traces: list[dict[str, Any]],
    context: dict[str, Any],
    prior_chronicle: str = "",
) -> LLMResponse:
    """Grounded one-line turn headline from mind traces — plain prose, not JSON."""
    del prior_chronicle  # kept for call-site compatibility; per-turn lines stay independent
    minds: list[dict[str, Any]] = []
    for t in traces:
        minds.append(
            {
                "creature": t.get("creature"),
                "action": t.get("action"),
                "target": t.get("target"),
                "glyphs": t.get("glyphs"),
                "intended_meaning": (t.get("intended_meaning") or "")[:120],
                "fallback": bool(t.get("fallback")),
            }
        )
    system = (
        "You are the forest chronicler for a glyph-only creature simulation. "
        "Write exactly ONE short sentence (max 22 words). "
        "Use ONLY the action and target fields for verbs — e.g. move_north means moved, "
        "signal means signaled, share_food means shared food, follow means followed. "
        "Never claim signal/follow/share unless action is exactly that. "
        "Name who acted and toward whom; mention glyphs only if central. "
        "No mood filler, no 'eerily quiet', no duplicate recap of prior turns. "
        "Use ONLY facts in the JSON. Plain English text only."
    )
    payload = {
        "turn": turn,
        "world": context,
        "minds_this_turn": minds,
    }
    user = f"One-sentence turn headline from trace data:\n{json.dumps(payload, ensure_ascii=True)}"
    return _route_prose(system, user)


def summarize_run_finale(
    turn_count: int,
    turn_headlines: list[dict[str, Any]],
    highlights: dict[str, Any],
) -> LLMResponse:
    """Closing summary for a stopped run — the interesting arc in a few sentences."""
    system = (
        "You are the forest chronicler closing a field journal after a glyph-only creature run. "
        "Write exactly 4-5 short sentences in past tense. Plain text — no lists, no markdown. "
        "REQUIRED — include one sentence naming highlights.glyph_drift.dominant_glyph and cite "
        "at least TWO creatures with DIFFERENT readings from highlights.glyph_drift.conflicting_readings "
        "(e.g. \"nilisi meant food to Nia and alert to Sora\"). Use the summary_line as a guide. "
        "REQUIRED — include one sentence on social bonds from highlights.social_bonds: "
        "who shared food with whom, who followed whom, and who trusted whom most. "
        "Use share_food_bonds, follow_bonds, and strongest_trust only. "
        "If highlights.stranger_arc.summary_line is non-empty, REQUIRED: one sentence on the stranger "
        "(name, dialect glyphs, or an interaction). "
        "REQUIRED final sentence: list highlights.final_turn_moves exactly — each creature and "
        "move direction/action from that list; do not invent different directions. "
        "Other sentences may cover deception or key actions from recent_traces. "
        "Warm tone is fine; cinematic fiction is not. "
        "Do NOT invent sunsets, dusk, dawn, campfires, fireflies, stargazing, journeys, travel, "
        "berries, mushrooms, meals by fire, or scenic closure absent from the traces. "
        "Never mention villages, towns, cities, homes, or leaving the forest. "
        "Only name creatures in creature_names. "
        "No generic filler — every sentence must cite concrete creatures, glyphs, or bonds from the JSON."
    )
    payload = {
        "turn_count": turn_count,
        "turn_headlines": turn_headlines,
        "highlights": highlights,
    }
    user = f"Write the forest epilogue:\n{json.dumps(payload, ensure_ascii=True)}"
    tok = int(os.environ.get("MOKU_RUN_SUMMARY_MAX_TOKENS", "220"))
    temp = float(os.environ.get("MOKU_RUN_SUMMARY_TEMPERATURE", "0.45"))
    return _route_prose(system, user, max_tokens=tok, temperature=temp)


def summarize_run_finale_repair(
    draft: str,
    turn_count: int,
    highlights: dict[str, Any],
) -> LLMResponse:
    """Rewrite a rejected epilogue — keep warmth, drop travel/place inventions."""
    system = (
        "Rewrite this forest epilogue in exactly 4-5 short past-tense sentences. "
        "Keep creature names, glyphs, and actions from the JSON highlights only. "
        "One sentence MUST name highlights.glyph_drift.dominant_glyph with two creatures "
        "and their conflicting readings. "
        "One sentence MUST describe social bonds: share_food, follow, or trust from "
        "highlights.social_bonds. "
        "If highlights.stranger_arc.summary_line exists, one sentence MUST use it. "
        "Final sentence MUST match highlights.final_turn_moves for each creature's action. "
        "Remove sunsets, dusk, campfires, fireflies, stars, journeys, travel, invented meals, "
        "and place names. No villages, towns, or leaving the forest. Plain text only."
    )
    payload = {"turn_count": turn_count, "highlights": highlights, "draft_to_fix": draft[:800]}
    user = f"Repair this epilogue:\n{json.dumps(payload, ensure_ascii=True)}"
    tok = int(os.environ.get("MOKU_RUN_SUMMARY_MAX_TOKENS", "320"))
    temp = float(os.environ.get("MOKU_RUN_SUMMARY_TEMPERATURE", "0.4"))
    return _route_prose(system, user, max_tokens=tok, temperature=temp)
