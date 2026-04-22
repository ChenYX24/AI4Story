// 浏览器语音识别 (webkitSpeechRecognition / SpeechRecognition)
// iOS Safari 不支持 — 调用方应通过 supported() 判断后再露出语音按钮
import { ref, onBeforeUnmount } from "vue";

declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

export function useASR(opts: { lang?: string } = {}) {
  const Cls = (window.SpeechRecognition || window.webkitSpeechRecognition) as any;
  const supported = !!Cls;
  const listening = ref(false);
  const transcript = ref("");
  let rec: any = null;

  function listenOnce(): Promise<string> {
    return new Promise((resolve, reject) => {
      if (!Cls) { reject(new Error("浏览器不支持语音识别")); return; }
      try {
        rec = new Cls();
        rec.lang = opts.lang || "zh-CN";
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        rec.continuous = false;
      } catch (e: any) { reject(e); return; }

      rec.onresult = (event: any) => {
        const t = event.results?.[0]?.[0]?.transcript || "";
        transcript.value = t;
        listening.value = false;
        resolve(t);
      };
      rec.onerror = (e: any) => { listening.value = false; reject(new Error(e.error || "asr error")); };
      rec.onend  = () => { listening.value = false; };

      listening.value = true;
      try { rec.start(); } catch (e: any) { listening.value = false; reject(e); }
    });
  }

  function abort() {
    try { rec?.abort?.(); } catch { /* noop */ }
    listening.value = false;
  }

  onBeforeUnmount(abort);

  return { supported, listening, transcript, listenOnce, abort };
}
