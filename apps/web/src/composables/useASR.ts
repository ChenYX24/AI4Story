// 浏览器语音识别 (webkitSpeechRecognition / SpeechRecognition)
// iOS Safari 不支持 — 调用方应通过 supported() 判断后再露出语音按钮
// 注意：webkitSpeechRecognition 走的是浏览器内置（Chrome 为 Google）的云端识别服务，
// 网络不稳定时会抛 "network"。这里对 network 做自动重试，并把错误码翻译成友好中文。
import { ref, onBeforeUnmount } from "vue";
import { useMicLevel } from "./useMicLevel";

declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

// 仅对网络类瞬时错误重试；no-speech / not-allowed 等重试无意义。
const RETRYABLE = new Set(["network"]);

const FRIENDLY: Record<string, string> = {
  "network": "网络不稳定，语音识别服务连接失败，请重试或改用键盘输入",
  "not-allowed": "麦克风权限被拒绝，请在浏览器地址栏允许麦克风后重试",
  "service-not-allowed": "麦克风权限被拒绝，请在浏览器允许麦克风后重试",
  "audio-capture": "没有检测到麦克风设备，请检查麦克风连接",
  "no-speech": "没听清，请再说一次",
  "aborted": "语音输入已取消",
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// 自己控制何时结束识别，避免引擎被背景杂音拖住一直不停：
const SILENCE_MS = 1400;    // 已识别到语音后，静默这么久就主动结束
const NO_SPEECH_MS = 7000;  // 一直没识别到任何语音，到点就放弃
const MAX_MS = 15000;       // 硬上限，无论如何到点结束

export function useASR(opts: { lang?: string; retries?: number } = {}) {
  const Cls = (window.SpeechRecognition || window.webkitSpeechRecognition) as any;
  const supported = !!Cls;
  const listening = ref(false);
  const transcript = ref("");
  const mic = useMicLevel();
  let rec: any = null;
  let micOn = false;
  let aborted = false;

  function startMicLevel() { if (!micOn) { micOn = true; mic.start(); } }
  function stopMicLevel() { if (micOn) { micOn = false; mic.stop(); } }

  function friendly(code: string, raw?: any): Error {
    const err = new Error(FRIENDLY[code] || `识别失败：${code || raw || "未知错误"}`);
    (err as any).code = code;
    return err;
  }

  // 单次识别尝试。成功 resolve 文本；失败 reject 一个带 .code 的 Error。
  // continuous + interimResults：由我们用静默计时器决定何时 stop()，而不是依赖
  // 引擎自己判停——后者在有背景杂音时常常永远不结束。
  function attempt(): Promise<string> {
    return new Promise((resolve, reject) => {
      try {
        rec = new Cls();
        rec.lang = opts.lang || "zh-CN";
        rec.interimResults = true;
        rec.maxAlternatives = 1;
        rec.continuous = true;
      } catch (e: any) { reject(friendly("", e)); return; }

      let settled = false;
      let finalText = "";
      let lastText = "";
      let gotSpeech = false;
      const startedAt = Date.now();
      let lastActivity = startedAt;
      let tick = 0;
      let maxTimer = 0;

      const cleanup = () => {
        if (tick) { clearInterval(tick); tick = 0; }
        if (maxTimer) { clearTimeout(maxTimer); maxTimer = 0; }
      };
      const done = (fn: () => void) => { if (!settled) { settled = true; cleanup(); fn(); } };
      const stopRec = () => { try { rec.stop(); } catch { /* noop */ } };

      rec.onresult = (event: any) => {
        let fin = "", interim = "";
        for (let i = 0; i < event.results.length; i++) {
          const r = event.results[i];
          if (r.isFinal) fin += r[0]?.transcript || "";
          else interim += r[0]?.transcript || "";
        }
        finalText = fin;
        const combined = (fin + interim).trim();
        if (combined) { transcript.value = combined; lastText = combined; gotSpeech = true; lastActivity = Date.now(); }
      };
      // onerror 给出具体错误码；onend 在我们 stop() 后触发——用累计文本 resolve。
      rec.onerror = (e: any) => done(() => reject(friendly(e?.error || "", e)));
      rec.onend = () => done(() => {
        const text = (finalText || lastText).trim();
        if (text) resolve(text);
        else reject(friendly("no-speech"));
      });

      try { rec.start(); } catch (e: any) { done(() => reject(friendly("", e))); return; }

      // 静默判停：识别到语音后静默 SILENCE_MS 就停；一直没语音则 NO_SPEECH_MS 后放弃。
      tick = window.setInterval(() => {
        const now = Date.now();
        if (gotSpeech) {
          if (now - lastActivity > SILENCE_MS) stopRec();
        } else if (now - startedAt > NO_SPEECH_MS) {
          stopRec();
        }
      }, 200);
      maxTimer = window.setTimeout(stopRec, MAX_MS); // 硬上限兜底
    });
  }

  async function listenOnce(): Promise<string> {
    if (!Cls) throw friendly("", "浏览器不支持语音识别");
    const maxRetries = opts.retries ?? 2;
    aborted = false;
    listening.value = true;
    startMicLevel();
    try {
      let lastErr: Error | null = null;
      for (let i = 0; i <= maxRetries; i++) {
        if (aborted) throw friendly("aborted");
        try {
          return await attempt();
        } catch (e: any) {
          lastErr = e;
          const code = (e as any)?.code || "";
          if (!RETRYABLE.has(code) || i === maxRetries) throw e;
          await sleep(250); // 网络抖动，稍等后重试
        }
      }
      throw lastErr || friendly("");
    } finally {
      listening.value = false;
      stopMicLevel();
    }
  }

  function abort() {
    aborted = true;
    try { rec?.abort?.(); } catch { /* noop */ }
    listening.value = false;
    stopMicLevel();
  }

  onBeforeUnmount(abort);

  return { supported, listening, transcript, listenOnce, abort };
}
