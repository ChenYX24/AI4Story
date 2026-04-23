// 并发预载整幕所有 storyboard lines 的音频 blob，点"下一句"零延迟。
// 设计：blob/audio 元素直到显式 disposeAll 才释放，允许同一行反复重播。
import { ref, onBeforeUnmount } from "vue";

export interface TTSControl {
  play(): Promise<void>;
  stop(): void;
  dispose(): void;
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
    return { play: async () => {}, stop: () => {}, dispose: () => {} };
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
    try { audio.pause(); } catch { /* */ }
    try { URL.revokeObjectURL(objectUrl); } catch { /* */ }
  };
  const ctrl: TTSControl = {
    play() {
      if (disposed) return Promise.resolve();
      if (currentCtrl && currentCtrl !== ctrl) { try { currentCtrl.stop(); } catch { /* */ } }
      currentCtrl = ctrl;
      try { audio.currentTime = 0; } catch { /* */ }
      return new Promise((resolve) => {
        const done = () => {
          audio.onended = null; audio.onerror = null;
          if (currentCtrl === ctrl) currentCtrl = null;
          resolve();
        };
        audio.onended = done; audio.onerror = done;
        audio.play().catch(done);
      });
    },
    stop() {
      // 仅暂停，不释放 blob —— 让后续点击/重播可用
      try { audio.pause(); } catch { /* */ }
      if (currentCtrl === ctrl) currentCtrl = null;
    },
    dispose,
  };
  return ctrl;
}

export function useTTSPreload() {
  const slots = ref<Array<Promise<TTSControl | null>>>([]);
  // 当前正在播放的行索引（-1 表示静默）—— 供 UI 脉冲高亮
  const playingIdx = ref(-1);

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
    if (!c) return;
    playingIdx.value = idx;
    try {
      await c.play();
    } finally {
      if (playingIdx.value === idx) playingIdx.value = -1;
    }
  }

  function stop() {
    try { currentCtrl?.stop(); } catch { /* */ }
    currentCtrl = null;
    playingIdx.value = -1;
  }

  async function disposeAll() {
    stop();
    const arr = slots.value.slice();
    slots.value = [];
    for (const p of arr) {
      try { const c = await p; c?.dispose(); } catch { /* */ }
    }
  }

  onBeforeUnmount(() => { void disposeAll(); });

  // 临时：给 chat reply 等即兴 TTS 用
  async function playOne(line: LineSpec) {
    try { (await fetchBlobCtrl(line)).play(); } catch { /* */ }
  }

  return { preload, play, stop, playOne, disposeAll, playingIdx };
}
