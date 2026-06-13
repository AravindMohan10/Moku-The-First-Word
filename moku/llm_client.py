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


def default_model() -> str:
    return os.environ.get(
        "MOKU_HF_MODEL",
        os.environ.get("MOKU_MODEL_NAME", "meta-llama/Llama-3.2-3B-Instruct"),
    ).strip()


def _model_fallbacks() -> list[str]:
    raw = os.environ.get(
        "MOKU_HF_MODEL_FALLBACKS",
        "meta-llama/Llama-3.2-3B-Instruct,Qwen/Qwen2.5-Coder-3B-Instruct,deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
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
    if _hf_token():
        return f"huggingface/{default_model()}"
    base = os.environ.get("MOKU_MODEL_BASE_URL", "").strip()
    if base:
        return f"local/{default_model()}"
    return "unconfigured"


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
    if not raw and os.environ.get("MOKU_JSON_MODE", "1") == "1":
        body["response_format"] = {"type": "json_object"}
    started = time.perf_counter()
    try:
        res = requests.post(
            f"{base_url.rstrip('/')}/v1/chat/completions",
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
                "reasoning_summary": (t.get("reasoning_summary") or "")[:180],
                "fallback": bool(t.get("fallback")),
            }
        )
    system = (
        "You are the forest chronicler for a glyph-only creature simulation. "
        "Write exactly ONE short sentence (max 22 words). "
        "Name who acted and toward whom; mention glyphs only if central. "
        "No mood filler, no 'eerily quiet', no duplicate recap of prior turns. "
        "Use ONLY facts in the JSON. Plain text only."
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
        "Describe only social moves from turn_headlines and recent_traces: who signaled whom, "
        "who share_food/gathered/moved, which glyphs spread. "
        "Warm tone is fine; cinematic fiction is not. "
        "Do NOT invent sunsets, dusk, dawn, campfires, stargazing, journeys, travel, berries, "
        "mushrooms, meals by fire, or emotional closure scenes absent from the traces. "
        "Never mention villages, towns, cities, homes, or leaving the forest. "
        "Only name creatures in creature_names. "
        "If one glyph dominates, say so — do not invent a day-long story arc."
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
        "Remove sunsets, dusk, campfires, stars, journeys, travel, invented meals, and place names. "
        "No villages, towns, or leaving the forest. Plain text only."
    )
    payload = {"turn_count": turn_count, "highlights": highlights, "draft_to_fix": draft[:800]}
    user = f"Repair this epilogue:\n{json.dumps(payload, ensure_ascii=True)}"
    tok = int(os.environ.get("MOKU_RUN_SUMMARY_MAX_TOKENS", "320"))
    temp = float(os.environ.get("MOKU_RUN_SUMMARY_TEMPERATURE", "0.4"))
    return _route_prose(system, user, max_tokens=tok, temperature=temp)
