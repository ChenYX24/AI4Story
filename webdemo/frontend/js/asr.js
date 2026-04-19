export function asrSupported() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export function listenOnce({ lang = "zh-CN", timeoutMs = 8000 } = {}) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return Promise.reject(new Error("ASR not supported"));
  const r = new SR();
  r.lang = lang;
  r.interimResults = false;
  r.maxAlternatives = 1;
  let finished = false;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      if (finished) return;
      finished = true;
      try { r.stop(); } catch (_) {}
      reject(new Error("timeout"));
    }, timeoutMs);
    r.onresult = (e) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      resolve(e.results[0][0].transcript);
    };
    r.onerror = (e) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      reject(new Error(e.error || "asr error"));
    };
    r.onend = () => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      reject(new Error("no speech"));
    };
    r.start();
  });
}
