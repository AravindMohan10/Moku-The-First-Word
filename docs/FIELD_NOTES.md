# Moku: The First Word — Field Notes

*Thousand Token Wood · Build Small Hackathon · [Live demo](https://huggingface.co/spaces/build-small-hackathon/moku-the-first-word) · [Trace on Hub](https://huggingface.co/datasets)*

---

## The forest had no dictionary. It got one anyway.

Picture six small creatures in a twilight grid. They cannot speak English. They cannot read a phrasebook. They can only invent short sounds — **glyphs** — and shout them at each other while they're hungry, scared, or feeling generous.

We built **Moku: The First Word** to answer a simple question:

> What happens when you give tiny LLM minds a fixed stage, zero vocabulary, and a rule that says *reuse what you hear*?

---

## Same sound. Six private dictionaries.

Here's the moment that sold us on the project.

Turn 13. A glyph called **`nilisi`** is everywhere — speech bubbles, signals, public chatter. One word. The forest is obsessed.

Open **Mind Traces** (our evidence layer, not the pretty prose) and compare readings:

| Creature | Hears `nilisi` as… |
|----------|-------------------|
| Nia | Share food |
| Sora | Alert |
| Pika | Useful signal maybe |
| Stray-6 | Useful signal maybe |

Same glyph. Different minds. No narrator assigned that. The model did.

That's not a bug. **That's the demo.**

We script the *pressure* — food on turn 2, a soft rain on turn 3 (clears turn 6), scarcity on turn 5, a stranger on turn 8, danger on turn 11, rain again on turn 14. We do **not** script who means what, who shares with whom, or which glyph becomes the forest's accidental meme.

---

## What is a glyph? (30 seconds, no linguistics degree)

A glyph is a made-up word: `brlu`, `nilisi`, `soliko`. Lowercase, 2–8 letters, not English, not a creature name.

Creatures **only** speak glyphs in public. Judges see bubbles, not subtitles.

Under the hood, each mind returns JSON every turn:

- **glyphs** — what it shouts  
- **interpretation** — private glosses for what it *heard*  
- **action** — move, gather, signal, share food, follow…  
- **trust_updates** — who it trusts more or less  
- **reasoning_summary** — English audit text for humans (not for them)

The English is the **microscope**, not the **phenomenon**. Like subtitles on a foreign film: the creatures aren't thinking in your language; you're just allowed to peek.

---

## Two engines, one forest

We split the work on purpose:

**Python owns physics and honesty.**

- Grid, hunger, fear, food, danger, shelter  
- Validation, JSON repair, target fixing  
- Trace logging, export, replay mode  
- Glyph drift stats, deception flags, social graph edges  

**The small LLM owns minds.**

- Which glyph to invent or echo  
- Who to signal, feed, follow, or ignore  
- How to interpret overheard sounds  
- What to store in memory  

If the model fails, we fall back to a rule policy — and we **mark it in the trace** (`fallback: true`). No silent cheating. Judges can grep for it.

---

## Memory without melting your API quota

Each creature gets its own namespace:

```text
world:{world_id}:creature:{creature_id}
```

We use **Mem0** for cloud persistence and mirror every write to **SQLite** locally.

Hackathon discovery: retrieval calls are precious (1,000/month on the free tier burns fast when six minds search every 2.5 seconds). Our fix:

- **Writes** → Mem0 (the integration story)  
- **Reads** → local mirror (same memories, zero search quota)  

Hybrid memory: production-shaped, demo-safe. The header literally says *mem0 (platform writes) + local retrieve*. We're not pretending.

---

## The model: small on purpose

We're targeting **OpenBMB MiniCPM3-4B** (4B — no exact "3B" checkpoint, still Tiny-Titan eligible) served via **Modal vLLM**, with HF fallbacks for dev.

Why not cloud inference for OpenBMB? It's often not on HF Inference Providers. So we ship the model ourselves — **LOCAL-FIRST** badge, OpenBMB sponsor lane, Modal awards lane, all one pipeline.

Fine-tuning path exists: golden traces → SFT JSONL → LoRA on Modal → merged weights. The forest teaches the forest.

---

## Watch it like a scientist, not a tourist

Press **Play**. Turn on every overlay (we default them on now — trust webs, signal arcs, speech, mood rings). You're not missing a secret panel.

**Three beats to watch for:**

1. **Turn 2–4** — first glyphs appear. Random-ish. Cute.  
2. **Turn 8** — stranger arrives. Social graph rewires.  
3. **Turn 13+** — one glyph dominates. Readings diverge. Someone shares food. Someone reads *alert*.  

Then **Stop**. Read the epilogue if you want poetry. Then open **Mind Traces** and **⬇ JSON** if you want truth.

The chronicle is garnish. The JSON is proof.

---

## Scripted vs emergent (we'll say it out loud)

| Scripted every sandbox run | Emergent every run |
|---------------------------|-------------------|
| Seed 42, six creatures, 9×9 map | Which glyphs are coined |
| Food T2 · scarcity T5 · stranger T8 · danger T11 · rain T14 | Which glyph spreads like a meme |
| Hunger/fear/trust mechanics | Who shares, follows, deceives |
| | Private meanings drifting apart |

Same stage. New language every time.

We put that split on the homepage because hackathon judges have seen too many "emergence" demos that mean *we random()'d the loot table*.

---

## What we didn't build (on purpose)

- **Not** a finance UI with a Patron and a magistrate  
- **Not** a one-model improv chat with a token counter  
- **Not** English speech with fantasy font  

We built **six parallel JSON minds** in a glowing forest observatory, with exportable audit trails.

Whimsical surface. Serious instrumentation underneath.

---

## Try it

- **Space:** `build-small-hackathon/moku-the-first-word`  
- **Repo:** [Moku-The-First-Word](https://github.com/) *(add your link)*  
- **Golden trace:** `world-8953-t33.json` — 33 turns of glyph drift, food sharing, stranger drama  
- **Replay:** `MOKU_REPLAY_TRACES=data/traces/world-8953-t33.json python app.py`  

One-line pitch if you're in a hurry:

> *Same hackathon track. They built a stock market. We built the first word.*

---

## What we learned

1. **Small models can carry social fiction** if you give them structure (JSON schema, visible traces, strict world rules).  
2. **Reuse beats invention** — the fun starts when one glyph wins and meanings split.  
3. **Honesty wins demos** — label what's scripted, export everything, mark fallbacks.  
4. **Hybrid memory is a hackathon superpower** — cloud story, local reliability, quota intact.  

The forest didn't need a dictionary.

It needed six minds, a microphone, and someone watching closely enough to catch the first lie.

---

*Built for the [Build Small Hackathon](https://huggingface.co/build-small-hackathon) · Thousand Token Wood track · OpenBMB MiniCPM3-4B · Mem0 · Modal · Gradio*
