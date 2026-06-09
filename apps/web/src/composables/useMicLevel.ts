// 麦克风实时电平 — 单例
// webkitSpeechRecognition 不暴露原始音频，无法画波形。这里并行用 getUserMedia + Web Audio
// AnalyserNode 采集麦克风时域数据，供波形组件读取。任意 useASR 监听时都会驱动同一个实例，
// 这样无论从哪个语音按钮起头，底部栏的波形都能显示。
import { ref } from "vue";

const active = ref(false);          // 是否正在采集（已拿到麦克风流）
const starting = ref(false);        // 正在请求麦克风（避免重复 getUserMedia）

let audioCtx: AudioContext | null = null;
let analyser: AnalyserNode | null = null;
let source: MediaStreamAudioSourceNode | null = null;
let stream: MediaStream | null = null;
let refCount = 0;                   // 支持多个 useASR 并发持有

/** 当前 AnalyserNode，未采集时为 null。波形组件从这里读 getByteTimeDomainData。 */
export function getMicAnalyser(): AnalyserNode | null {
  return active.value ? analyser : null;
}

async function start() {
  refCount++;
  if (active.value || starting.value) return;
  starting.value = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    // 用户已经松手/识别结束 — 拿到流也立刻丢弃
    if (refCount === 0) { stream.getTracks().forEach((t) => t.stop()); stream = null; return; }
    const Ctx = window.AudioContext || (window as any).webkitAudioContext;
    audioCtx = new Ctx();
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 1024;
    analyser.smoothingTimeConstant = 0.45;
    source = audioCtx.createMediaStreamSource(stream);
    source.connect(analyser);
    active.value = true;
  } catch {
    // 拿不到麦克风（权限拒绝等）— 静默失败，语音识别本身的报错另有提示
    teardown();
  } finally {
    starting.value = false;
  }
}

function stop() {
  refCount = Math.max(0, refCount - 1);
  if (refCount === 0) teardown();
}

function teardown() {
  active.value = false;
  try { source?.disconnect(); } catch { /* noop */ }
  try { audioCtx?.close(); } catch { /* noop */ }
  stream?.getTracks().forEach((t) => t.stop());
  source = null;
  analyser = null;
  audioCtx = null;
  stream = null;
}

export function useMicLevel() {
  return { active, start, stop, getMicAnalyser };
}
