// 并发预载整幕所有 storyboard lines 的音频 blob，点"下一句"零延迟
import { ref, onBeforeUnmount } from "vue";

export interface TTSControl {
  play(): Promise<void>;
  stop(): void;
}

export interface LineSpec {
  text: string;
  speaker?: string;
  tone?: string;
}

let currentCtrl: TTSControl | null = null;

function buildUrl(line: LineSpec): string {
  const q = new URLSearchParams({ text: line.text });
  if (line.speaker) q.set("speaker", line.speaker);
  if (line.tone) q.set("tone", line.tone);
  return `/api/tts?${q.toString()}`;
}

async function fetchBlobCtrl(line: LineSpec): Promise<TTSControl> {
  if (!line.text?.trim()) {
    return { play: async () => {}, stop: () => {} };
  }
  const resp = await fetch(buildUrl(line));
  if (!resp.ok) throw new Error(`tts HTTP ${resp.status}`);
  const blob = await resp.blob();
  const objectUrl = URL.createObjectURL(blob);
  const audio = new Audio(objectUrl);
  audio.preload = "auto";
  let disposed = false;
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    try { URL.revokeObjectURL(objectUrl); } catch { /* noop */ }
  };
  const ctrl: TTSControl = {
    play() {
      if (currentCtrl && currentCtrl !== ctrl) { try { currentCtrl.stop(); } catch { /* */ } }
      currentCtrl = ctrl;
      return new Promise((resolve) => {
        const done = () => { if (currentCtrl === ctrl) currentCtrl = null; dispose(); resolve(); };
        audio.onended = done; audio.onerror = done;
        audio.play().catch(done);
      });
    },
    stop() {
      try { audio.pause(); } catch { /* */ }
      dispose();
    },
  };
  return ctrl;
}

export function useTTSPreload() {
  const slots = ref<Array<Promise<TTSControl | null>>>([]);

  function preload(lines: LineSpec[]) {
    disposeAll();
    slots.value = lines.map((ln) =>
      fetchBlobCtrl(ln).catch((e) => {
        console.warn("tts preload:", e?.message || e);
        return null;
      }),
    );
  }

  async function play(idx: number) {
    const p = slots.value[idx];
    if (!p) return;
    const c = await p;
    if (c) await c.play();
  }

  function stop() {
    try { currentCtrl?.stop(); } catch { /* */ }
    currentCtrl = null;
  }

  async function disposeAll() {
    stop();
    const arr = slots.value.slice();
    slots.value = [];
    for (const p of arr) {
      try { const c = await p; c?.stop(); } catch { /* */ }
    }
  }

  onBeforeUnmount(() => { void disposeAll(); });

  // 临时：给 chat reply 等即兴 TTS 用
  async function playOne(line: LineSpec) {
    try { (await fetchBlobCtrl(line)).play(); } catch { /* */ }
  }

  return { preload, play, stop, playOne, disposeAll };
}
