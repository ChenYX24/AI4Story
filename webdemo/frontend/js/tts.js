import { ttsUrl } from "./api.js";

let current = null;

export function stopTTS() {
  if (current) {
    try { current.stop(); } catch (_) {}
    current = null;
  }
}

/**
 * Pre-fetch the TTS audio as a blob and return a controller.
 * The caller decides WHEN to call play(), so text display can be synced
 * to the moment audio actually starts.
 */
export async function preloadTTS(text, { voice, tone, speaker } = {}) {
  if (!text || !text.trim()) {
    return { play: async () => {}, stop: () => {} };
  }
  const url = ttsUrl(text, { voice, tone, speaker });
  const resp = await fetch(url);
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { const b = await resp.json(); if (b?.detail) detail = b.detail; } catch (_) {}
    throw new Error(detail);
  }
  const blob = await resp.blob();
  const objectUrl = URL.createObjectURL(blob);
  const audio = new Audio(objectUrl);
  audio.preload = "auto";
  let disposed = false;
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    try { URL.revokeObjectURL(objectUrl); } catch (_) {}
  };
  const ctrl = {
    audio,
    play() {
      stopTTS();
      current = ctrl;
      return new Promise((resolve) => {
        const done = () => {
          if (current === ctrl) current = null;
          dispose();
          resolve();
        };
        audio.onended = done;
        audio.onerror = done;
        audio.play().catch(done);
      });
    },
    stop() {
      try { audio.pause(); } catch (_) {}
      dispose();
    },
  };
  return ctrl;
}

/** Fire-and-forget. Used for non-synced hints (like the interaction_goal intro). */
export async function playTTS(text, opts) {
  try {
    const ctrl = await preloadTTS(text, opts);
    await ctrl.play();
  } catch (e) {
    console.warn("playTTS:", e.message);
  }
}
