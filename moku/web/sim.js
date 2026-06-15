function setPanelOpen(open) {
  const panel = document.getElementById("moku-side-panel");
  if (!panel) return;
  panel.classList.toggle("open", open);
  sessionStorage.setItem("moku-panel-open", open ? "1" : "0");
}

function setGuideOpen(open) {
  const guide = document.getElementById("moku-guide-panel");
  if (!guide) return;
  guide.classList.toggle("open", open);
  sessionStorage.setItem("moku-guide-open", open ? "1" : "0");
}

function restorePanelState() {
  if (sessionStorage.getItem("moku-panel-open") === "1") {
    document.getElementById("moku-side-panel")?.classList.add("open");
  }
}

function restoreGuideState() {
  if (sessionStorage.getItem("moku-guide-open") === "1") {
    document.getElementById("moku-guide-panel")?.classList.add("open");
  }
}

/* ── Forest soundscape: soothing bed + creature/event accents ── */
const MOKU_SOUND_KEY = "moku-sound";

const mokuAudio = {
  ctx: null,
  master: null,
  muted: sessionStorage.getItem(MOKU_SOUND_KEY) === "0",
  loops: {},
  lastAmbientKey: "",
  lastBeatKey: "",
  lastBondsKey: "",
  lastSignalsKey: "",
  lastEventKey: "",
  playing: false,
  bootstrapped: false,
  _pendingResume: false,
  _unlockChirped: false,

  /** Master bus — kept high enough to hear on laptop speakers. */
  _masterLevel() {
    return this.muted ? 0 : 0.58;
  },

  ensureCtx() {
    if (this.ctx) return this.ctx;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    this.ctx = new Ctx();
    this.master = this.ctx.createGain();
    this.master.gain.value = this._masterLevel();
    this.master.connect(this.ctx.destination);
    return this.ctx;
  },

  async resume() {
    const ctx = this.ensureCtx();
    if (!ctx) return false;
    try {
      if (ctx.state === "suspended") await ctx.resume();
    } catch (_) {
      return false;
    }
    return ctx.state === "running";
  },

  setMuted(muted) {
    this.muted = muted;
    sessionStorage.setItem(MOKU_SOUND_KEY, muted ? "0" : "1");
    if (this.master) this.master.gain.value = this._masterLevel();
    if (muted) this.stopAllLoops();
  },

  stopAllLoops() {
    Object.values(this.loops).forEach((node) => {
      try {
        node.stop?.();
        node.disconnect?.();
      } catch (_) {}
    });
    this.loops = {};
  },

  _noiseBuffer(duration = 2, bright = false) {
    const ctx = this.ensureCtx();
    const len = Math.floor(ctx.sampleRate * duration);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = buf.getChannelData(0);
    let last = 0;
    for (let i = 0; i < len; i++) {
      const white = Math.random() * 2 - 1;
      last = last * (bright ? 0.97 : 0.988) + white * (bright ? 0.04 : 0.012);
      data[i] = last * (bright ? 4 : 2.2);
    }
    return buf;
  },

  _startLoop(name, setupFn) {
    if (this.loops[name] || this.muted) return;
    try {
      const node = setupFn(this.ensureCtx());
      if (node) this.loops[name] = node;
    } catch (err) {
      console.warn("moku loop failed:", name, err);
    }
  },

  _stopLoop(name, fadeSec = 0) {
    const node = this.loops[name];
    if (!node) return;
    if (fadeSec > 0 && typeof node.fadeOut === "function") {
      node.fadeOut(fadeSec);
      delete this.loops[name];
      return;
    }
    try {
      node.stop?.();
      node.disconnect?.();
    } catch (_) {}
    delete this.loops[name];
  },

  _toMaster(node, gain = 1) {
    const g = this.ctx.createGain();
    g.gain.value = gain;
    node.connect(g);
    g.connect(this.master);
    return g;
  },

  _buildDawnPad(ctx) {
    const t = ctx.currentTime;
    const bus = ctx.createGain();
    bus.gain.setValueAtTime(0, t);
    bus.gain.linearRampToValueAtTime(1, t + 5);

    const oscs = [];
    [
      [73.42, 0.027],
      [110.0, 0.024],
      [146.83, 0.020],
      [220.0, 0.014],
    ].forEach(([freq, vol], i) => {
      const osc = ctx.createOscillator();
      osc.type = i < 2 ? "sine" : "triangle";
      osc.frequency.value = freq * (1 + (i - 1.5) * 0.003);
      const g = ctx.createGain();
      g.gain.value = vol;
      osc.connect(g);
      g.connect(bus);
      osc.start(t);
      oscs.push(osc);
    });

    const breeze = ctx.createBufferSource();
    breeze.buffer = this._noiseBuffer(10);
    breeze.loop = true;
    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 280;
    const breezeGain = ctx.createGain();
    breezeGain.gain.value = 0.038;
    breeze.connect(filter);
    filter.connect(breezeGain);
    breezeGain.connect(bus);
    breeze.start(t);

    bus.connect(this.master);

    const stopParts = () => {
      oscs.forEach((o) => {
        try {
          o.stop();
        } catch (_) {}
      });
      try {
        breeze.stop();
      } catch (_) {}
      try {
        bus.disconnect();
      } catch (_) {}
    };

    return {
      fadeOut(duration = 5) {
        const now = ctx.currentTime;
        bus.gain.cancelScheduledValues(now);
        bus.gain.setValueAtTime(bus.gain.value, now);
        bus.gain.linearRampToValueAtTime(0, now + duration);
        setTimeout(stopParts, duration * 1000 + 150);
      },
      stop: stopParts,
      disconnect: () => bus.disconnect(),
    };
  },

  _fantasyFluteTone(ctx, t, freq, gain, duration = 3.2) {
    const bus = ctx.createGain();
    bus.gain.setValueAtTime(0, t);
    bus.gain.linearRampToValueAtTime(gain, t + 0.35);
    bus.gain.linearRampToValueAtTime(gain * 0.55, t + duration * 0.45);
    bus.gain.exponentialRampToValueAtTime(0.001, t + duration);

    const tone = ctx.createOscillator();
    tone.type = "sine";
    tone.frequency.setValueAtTime(freq * 0.992, t);
    tone.frequency.exponentialRampToValueAtTime(freq, t + 0.28);

    const whisper = ctx.createOscillator();
    whisper.type = "sine";
    whisper.frequency.setValueAtTime(freq * 2.01, t);
    const whisperG = ctx.createGain();
    whisperG.gain.value = 0.22;

    const vib = ctx.createOscillator();
    vib.frequency.value = 4.1;
    const vibDepth = ctx.createGain();
    vibDepth.gain.value = 1.1;
    vib.connect(vibDepth);
    vibDepth.connect(tone.frequency);

    const filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.setValueAtTime(680, t);
    filter.frequency.linearRampToValueAtTime(1180, t + 0.4);
    filter.frequency.exponentialRampToValueAtTime(920, t + duration);
    filter.Q.value = 0.4;

    tone.connect(filter);
    whisper.connect(whisperG);
    whisperG.connect(filter);

    const air = ctx.createBufferSource();
    air.buffer = this._noiseBuffer(0.25);
    const airF = ctx.createBiquadFilter();
    airF.type = "bandpass";
    airF.frequency.value = freq * 1.6;
    airF.Q.value = 2.5;
    const airG = ctx.createGain();
    airG.gain.setValueAtTime(0, t);
    airG.gain.linearRampToValueAtTime(gain * 0.35, t + 0.2);
    airG.gain.exponentialRampToValueAtTime(0.001, t + duration * 0.7);
    air.connect(airF);
    airF.connect(airG);
    airG.connect(bus);

    filter.connect(bus);
    this._toMaster(bus, 0.85);

    tone.start(t);
    whisper.start(t);
    vib.start(t);
    air.start(t);
    tone.stop(t + duration + 0.05);
    whisper.stop(t + duration + 0.05);
    vib.stop(t + duration + 0.05);
    air.stop(t + duration * 0.75);
  },

  _buildFluteBed(ctx) {
    const t = ctx.currentTime;
    const bus = ctx.createGain();
    bus.gain.setValueAtTime(0, t);
    bus.gain.linearRampToValueAtTime(1, t + 3);

    const warm = ctx.createBiquadFilter();
    warm.type = "lowpass";
    warm.frequency.value = 1800;
    warm.Q.value = 0.35;

    const shimmer = ctx.createOscillator();
    shimmer.type = "sine";
    shimmer.frequency.value = 0.11;
    const shimmerDepth = ctx.createGain();
    shimmerDepth.gain.value = 120;
    shimmer.connect(shimmerDepth);
    shimmerDepth.connect(warm.frequency);

    const root = ctx.createOscillator();
    root.type = "sine";
    root.frequency.value = 146.83;
    const rootG = ctx.createGain();
    rootG.gain.value = 0.018;
    root.connect(rootG);
    rootG.connect(warm);

    const fifth = ctx.createOscillator();
    fifth.type = "sine";
    fifth.frequency.value = 220.0;
    const fifthG = ctx.createGain();
    fifthG.gain.value = 0.012;
    fifth.connect(fifthG);
    fifthG.connect(warm);

    const mist = ctx.createBufferSource();
    mist.buffer = this._noiseBuffer(14);
    mist.loop = true;
    const mistF = ctx.createBiquadFilter();
    mistF.type = "bandpass";
    mistF.frequency.value = 520;
    mistF.Q.value = 0.55;
    const mistG = ctx.createGain();
    mistG.gain.value = 0.012;
    mist.connect(mistF);
    mistF.connect(mistG);
    mistG.connect(warm);

    warm.connect(bus);
    bus.connect(this.master);
    root.start(t);
    fifth.start(t);
    mist.start(t);
    shimmer.start(t);

    // D minor pentatonic — soft forest-pipe phrases, often rests
    const phrase = [293.66, 349.23, 392.0, 440.0, 523.25, 440.0, 392.0, 349.23, 293.66, null];
    let step = Math.floor(Math.random() * 4);
    let alive = true;

    const melodyTimer = setInterval(() => {
      if (!alive || this.muted || !this.playing) return;
      const note = phrase[step % phrase.length];
      step += 1;
      if (note == null) return;
      if (Math.random() < 0.22) return;
      this._fantasyFluteTone(this.ctx, this.ctx.currentTime, note, 0.032 + Math.random() * 0.010);
    }, 5200);

    const stopParts = () => {
      alive = false;
      clearInterval(melodyTimer);
      try {
        root.stop();
      } catch (_) {}
      try {
        fifth.stop();
      } catch (_) {}
      try {
        mist.stop();
      } catch (_) {}
      try {
        shimmer.stop();
      } catch (_) {}
      try {
        warm.disconnect();
      } catch (_) {}
      try {
        bus.disconnect();
      } catch (_) {}
    };

    return {
      melodyTimer,
      stop: stopParts,
      disconnect: () => bus.disconnect(),
    };
  },

  _fluteNote(freq, gain = 0.014) {
    this._oneShot((ctx, t) => this._fantasyFluteTone(ctx, t, freq, gain));
  },

  _oneShot(setupFn) {
    if (this.muted || !this.playing) return;
    const ctx = this.ensureCtx();
    if (!ctx || ctx.state !== "running") return;
    setupFn(ctx, ctx.currentTime);
  },

  _bubblePop(pitch = 1) {
    this._oneShot((ctx, t) => {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.setValueAtTime(520 * pitch, t);
      osc.frequency.exponentialRampToValueAtTime(90, t + 0.11);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(0.10, t + 0.012);
      g.gain.exponentialRampToValueAtTime(0.001, t + 0.14);
      osc.connect(g);
      this._toMaster(g);

      const pop = ctx.createBufferSource();
      pop.buffer = this._noiseBuffer(0.06, true);
      const pf = ctx.createBiquadFilter();
      pf.type = "highpass";
      pf.frequency.value = 1200;
      const pg = ctx.createGain();
      pg.gain.setValueAtTime(0.038, t);
      pg.gain.exponentialRampToValueAtTime(0.001, t + 0.05);
      pop.connect(pf);
      pf.connect(pg);
      this._toMaster(pg);
      osc.start(t);
      osc.stop(t + 0.16);
      pop.start(t);
      pop.stop(t + 0.06);
    });
  },

  _whoosh(pan = 0) {
    this._oneShot((ctx, t) => {
      const src = ctx.createBufferSource();
      src.buffer = this._noiseBuffer(0.35, true);
      const bp = ctx.createBiquadFilter();
      bp.type = "bandpass";
      bp.frequency.setValueAtTime(900 + pan * 120, t);
      bp.frequency.exponentialRampToValueAtTime(180, t + 0.22);
      bp.Q.value = 1.2;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(0.05, t + 0.03);
      g.gain.exponentialRampToValueAtTime(0.001, t + 0.28);
      src.connect(bp);
      bp.connect(g);
      this._toMaster(g);
      src.start(t);
      src.stop(t + 0.3);
    });
  },

  _signalPing() {
    this._oneShot((ctx, t) => {
      [740, 988].forEach((freq, i) => {
        const osc = ctx.createOscillator();
        osc.type = "sine";
        const start = t + i * 0.07;
        osc.frequency.setValueAtTime(freq, start);
        const g = ctx.createGain();
        g.gain.setValueAtTime(0, start);
        g.gain.linearRampToValueAtTime(0.055, start + 0.015);
        g.gain.exponentialRampToValueAtTime(0.001, start + 0.18);
        osc.connect(g);
        this._toMaster(g);
        osc.start(start);
        osc.stop(start + 0.2);
      });
    });
  },

  _trustBloom() {
    this._oneShot((ctx, t) => {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.setValueAtTime(130, t);
      osc.frequency.linearRampToValueAtTime(260, t + 0.45);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(0.06, t + 0.08);
      g.gain.exponentialRampToValueAtTime(0.001, t + 0.55);
      osc.connect(g);
      this._toMaster(g);
      osc.start(t);
      osc.stop(t + 0.6);

      this._bubblePop(0.85);
    });
  },

  _pluck(freq = 392) {
    this._oneShot((ctx, t) => {
      const osc = ctx.createOscillator();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(freq, t);
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.10, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + 0.22);
      osc.connect(g);
      this._toMaster(g);
      osc.start(t);
      osc.stop(t + 0.24);
    });
  },

  _playActionSound(action) {
    if (!action) return;
    if (action.startsWith("move_")) {
      const pan = action.includes("east") ? 1 : action.includes("west") ? -1 : 0;
      this._whoosh(pan);
      return;
    }
    const map = {
      signal: () => this._signalPing(),
      gather: () => {
        this._pluck(440);
        this._bubblePop(1.1);
      },
      share_food: () => {
        this._bubblePop(0.95);
        this._pluck(330);
      },
      follow: () => this._whoosh(0.4),
      hide: () => this._pluck(220),
      stay: () => this._bubblePop(0.75),
    };
    (map[action] || (() => this._bubblePop()))();
  },

  _ambientKey(scene, playing) {
    if (!scene) return "";
    return [
      playing ? "1" : "0",
      scene.dataset.turn || "",
      scene.dataset.weather || "",
      scene.dataset.scarcity || "",
      scene.dataset.event || "",
    ].join("|");
  },

  _handleCreatureSounds(scene) {
    const beat = scene.dataset.beat || "";
    const bonds = scene.dataset.bonds || "";
    const signals = scene.dataset.signals || "";

    if (beat && beat !== this.lastBeatKey) {
      this.lastBeatKey = beat;
      const action = beat.split("|")[1] || "";
      if (this.bootstrapped) this._playActionSound(action);
    }

    if (bonds !== this.lastBondsKey) {
      const prev = this.lastBondsKey ? this.lastBondsKey.split("|").filter(Boolean) : [];
      const next = bonds ? bonds.split("|").filter(Boolean) : [];
      if (this.bootstrapped && next.length > prev.length) this._trustBloom();
      this.lastBondsKey = bonds;
    }

    if (signals !== this.lastSignalsKey) {
      const prev = this.lastSignalsKey ? this.lastSignalsKey.split("|").filter(Boolean) : [];
      const next = signals ? signals.split("|").filter(Boolean) : [];
      if (this.bootstrapped && next.length > prev.length) this._signalPing();
      this.lastSignalsKey = signals;
    }

    if (!this.bootstrapped) this.bootstrapped = true;
  },

  _unlockChirp() {
    if (this._unlockChirped || this.muted) return;
    this._unlockChirped = true;
    this._pluck(523.25);
    setTimeout(() => this._bubblePop(1.05), 180);
  },

  _ensureLoops(weather, scarcity, turn) {
    if (this.master && !this.muted && this.master.gain.value < 0.05) {
      this.master.gain.value = this._masterLevel();
    }

    const dawnPhase = turn <= 1 && weather !== "rain";

    if (dawnPhase) {
      if (!this.loops.dawn) {
        this._stopLoop("flute");
        this._startLoop("dawn", (ctx) => this._buildDawnPad(ctx));
        this._unlockChirp();
      }
    } else {
      if (this.loops.dawn) this._stopLoop("dawn", 2);

      if (weather === "clear" && !this.loops.flute && !this.loops.rain) {
        this._startLoop("flute", (ctx) => this._buildFluteBed(ctx));
        this._unlockChirp();
      }
    }

    if (weather === "rain" && !this.loops.rain) {
      this._stopLoop("dawn");
      this._stopLoop("flute");
      this._startLoop("rain", (ctx) => {
        const src = ctx.createBufferSource();
        src.buffer = this._noiseBuffer(5);
        src.loop = true;
        const filter = ctx.createBiquadFilter();
        filter.type = "lowpass";
        filter.frequency.value = 850;
        const g = ctx.createGain();
        g.gain.value = 0.13;
        src.connect(filter);
        filter.connect(g);
        g.connect(this.master);
        src.start();
        return { stop: () => src.stop(), disconnect: () => g.disconnect() };
      });
      this._unlockChirp();
    } else if (weather !== "rain") {
      this._stopLoop("rain");
    }

    if (scarcity >= 3 && !this.loops.scarcity) {
      this._startLoop("scarcity", (ctx) => {
        const osc = ctx.createOscillator();
        osc.type = "sine";
        osc.frequency.value = 44;
        const g = ctx.createGain();
        g.gain.value = 0.033;
        osc.connect(g);
        g.connect(this.master);
        osc.start();
        return { stop: () => osc.stop(), disconnect: () => g.disconnect() };
      });
    } else if (scarcity < 3) {
      this._stopLoop("scarcity");
    }
  },

  async syncFromScene(scene, playing, force = false) {
    if (!scene) return;

    this.playing = playing;
    const running = await this.resume();

    if (!playing || this.muted) {
      this.lastAmbientKey = this._ambientKey(scene, playing);
      this.stopAllLoops();
      return;
    }

    if (!running || this.ctx?.state !== "running") {
      if (!this._pendingResume) {
        this._pendingResume = true;
        setTimeout(() => {
          this._pendingResume = false;
          mokuScheduleAudio(true);
        }, 400);
      }
      return;
    }

    this._handleCreatureSounds(scene);

    const weather = scene.dataset.weather || "clear";
    const scarcity = parseInt(scene.dataset.scarcity || "0", 10);
    const event = scene.dataset.event || "";
    const turn = parseInt(scene.dataset.turn || "0", 10);

    this._ensureLoops(weather, scarcity, turn);

    const ambientKey = this._ambientKey(scene, playing);
    if (!force && ambientKey === this.lastAmbientKey) return;
    this.lastAmbientKey = ambientKey;

    const t = (event || "").toLowerCase();
    if (t && !t.includes("quiet") && event !== this.lastEventKey) {
      this.lastEventKey = event;
      if (this.bootstrapped) {
        if (t.includes("stray") || t.includes("stranger")) this._pluck(196);
        else if (t.includes("fruit") || t.includes("food")) this._bubblePop(1.15);
        else if (t.includes("rain")) this._whoosh(-0.3);
      }
    }
  },
};

window.mokuAudio = mokuAudio;

function mokuFindSim() {
  const viewport = document.querySelector(".moku-sim-viewport");
  if (viewport) {
    return {
      viewport,
      root: viewport.querySelector(".moku-sim-root"),
      scene: viewport.querySelector(".world-scene"),
    };
  }
  return {
    viewport: null,
    root: document.querySelector(".moku-sim-root"),
    scene: document.querySelector(".world-scene"),
  };
}

async function mokuReadScene(force = false) {
  try {
    const { root, scene } = mokuFindSim();
    await mokuAudio.syncFromScene(scene, root?.dataset.playing === "1", force);
  } catch (err) {
    console.warn("moku audio sync:", err);
  }
}

let uiTickScheduled = false;
let audioTickScheduled = false;
let audioForceNext = false;

function mokuScheduleUi() {
  if (uiTickScheduled) return;
  uiTickScheduled = true;
  requestAnimationFrame(() => {
    uiTickScheduled = false;
    restorePanelState();
    restoreGuideState();
    mokuBindSoundToggle();
  });
}

function mokuScheduleAudio(force = false) {
  if (force) audioForceNext = true;
  mokuAttachObservers();
  if (audioTickScheduled) return;
  audioTickScheduled = true;
  setTimeout(() => {
    audioTickScheduled = false;
    const runForce = audioForceNext;
    audioForceNext = false;
    void mokuReadScene(runForce);
  }, 150);
}

function mokuFindSoundCheckbox() {
  const wrap = document.getElementById("ov-sound");
  if (!wrap) return null;
  return (
    wrap.querySelector("input[type='checkbox']") ||
    wrap.querySelector("[role='checkbox']") ||
    wrap.querySelector("input")
  );
}

function mokuBindSoundToggle() {
  const cb = mokuFindSoundCheckbox();
  if (!cb || cb.dataset.mokuBound === "1") return;
  cb.dataset.mokuBound = "1";
  const on = sessionStorage.getItem(MOKU_SOUND_KEY) !== "0";
  if ("checked" in cb) cb.checked = on;
  else cb.setAttribute("aria-checked", on ? "true" : "false");
  mokuAudio.setMuted(!on);
  cb.addEventListener("change", () => {
    const enabled = "checked" in cb ? cb.checked : cb.getAttribute("aria-checked") === "true";
    mokuAudio.setMuted(!enabled);
    if (enabled) mokuAudio.resume().then(() => mokuScheduleAudio(true));
  });
}

function mokuTryBoot() {
  const { root, scene } = mokuFindSim();
  if (!root && !scene) return false;
  mokuAttachObservers();
  mokuScheduleUi();
  mokuScheduleAudio(true);
  return true;
}

function mokuDebugState() {
  const { root, scene, viewport } = mokuFindSim();
  return {
    booted: !!viewport?.dataset.mokuAudioObs,
    scene: !!scene,
    playing: root?.dataset.playing ?? null,
    muted: mokuAudio.muted,
    ctx: mokuAudio.ctx?.state ?? "none",
    masterGain: mokuAudio.master?.gain.value ?? null,
    loops: Object.keys(mokuAudio.loops),
    soundKey: sessionStorage.getItem(MOKU_SOUND_KEY),
  };
}

async function mokuRestartAudio() {
  mokuAudio.stopAllLoops();
  mokuAudio._unlockChirped = false;
  mokuAudio.lastAmbientKey = "";
  await mokuAudio.resume();
  if (mokuAudio.master) mokuAudio.master.gain.value = mokuAudio._masterLevel();
  await mokuReadScene(true);
}

async function mokuTestSound() {
  mokuAudio.setMuted(false);
  mokuAudio.playing = true;
  const ok = await mokuAudio.resume();
  if (mokuAudio.master) mokuAudio.master.gain.value = mokuAudio._masterLevel();
  mokuAudio._pluck(440);
  mokuAudio._signalPing();
  return { ok, masterGain: mokuAudio.master?.gain.value ?? null };
}

window.mokuReadScene = mokuReadScene;
window.mokuScheduleAudio = mokuScheduleAudio;
window.mokuBindSoundToggle = mokuBindSoundToggle;
window.mokuTryBoot = mokuTryBoot;
window.mokuDebugState = mokuDebugState;
window.mokuRestartAudio = mokuRestartAudio;
window.mokuTestSound = mokuTestSound;

document.addEventListener(
  "click",
  () => {
    try {
      mokuAudio.resume().then((ok) => {
        if (ok && mokuAudio.master) {
          mokuAudio.master.gain.value = mokuAudio._masterLevel();
        }
        mokuScheduleAudio(true);
      });
    } catch (_) {}
  },
  { capture: true },
);

document.addEventListener("click", (e) => {
  if (e.target.closest("#moku-guide-btn") || e.target.closest("#moku-guide-close")) {
    e.preventDefault();
    const guide = document.getElementById("moku-guide-panel");
    setGuideOpen(!guide?.classList.contains("open"));
    return;
  }
  if (e.target.closest(".moku-panel-btn")) {
    e.preventDefault();
    const panel = document.getElementById("moku-side-panel");
    setPanelOpen(!panel?.classList.contains("open"));
    return;
  }
  const panel = document.getElementById("moku-side-panel");
  if (panel?.classList.contains("open") && !e.target.closest(".moku-side-panel")) {
    if (e.target.closest(".sim-world-wrap") || e.target.closest(".world-scene")) {
      setPanelOpen(false);
    }
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const guide = document.getElementById("moku-guide-panel");
  if (guide?.classList.contains("open")) {
    setGuideOpen(false);
    return;
  }
  setPanelOpen(false);
});

const uiObserver = new MutationObserver(() => mokuScheduleUi());
const audioObserver = new MutationObserver(() => mokuScheduleAudio());

function mokuAttachObservers() {
  const panelHost = document.getElementById("moku-panel-host");
  if (panelHost && !panelHost.dataset.mokuUiObs) {
    panelHost.dataset.mokuUiObs = "1";
    uiObserver.observe(panelHost, { childList: true, subtree: true });
  }
  const viewport = document.querySelector(".moku-sim-viewport");
  if (viewport && !viewport.dataset.mokuAudioObs) {
    viewport.dataset.mokuAudioObs = "1";
    audioObserver.observe(viewport, { childList: true, subtree: true });
  }
  mokuScheduleUi();
}

window.mokuAttachObservers = mokuAttachObservers;

setInterval(() => mokuTryBoot(), 800);

setInterval(() => {
  const { root, scene } = mokuFindSim();
  if (!scene || mokuAudio.muted) return;
  if (root?.dataset.playing !== "1") return;
  void mokuAudio.resume().then((running) => {
    if (!running) return;
    const loopCount = Object.keys(mokuAudio.loops).length;
    if (loopCount === 0) void mokuReadScene(true);
  });
}, 2500);

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mokuTryBoot);
} else {
  mokuTryBoot();
}
