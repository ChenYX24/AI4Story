let timer = null;

export function toast(message, ms = 2200) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(timer);
  timer = setTimeout(() => el.classList.remove("show"), ms);
}

export function showLoader(text = "AI 正在作画…") {
  const el = document.getElementById("loader");
  const t = document.getElementById("loader-text");
  if (t) t.textContent = text;
  el?.classList.remove("hidden");
}

export function hideLoader() {
  document.getElementById("loader")?.classList.add("hidden");
}

const HINTS = [
  "AI 正在调色盘里挑颜色…",
  "小画笔正在认真地画…",
  "把你说的故事变成画…",
  "再加一点点魔法…",
  "快完成啦，再等一下～",
];

let hintTimer = null;
export function startHintRotation() {
  let i = 0;
  const t = document.getElementById("loader-text");
  hintTimer = setInterval(() => {
    if (!t) return;
    t.textContent = HINTS[i % HINTS.length];
    i += 1;
  }, 3500);
}

export function stopHintRotation() {
  clearInterval(hintTimer);
  hintTimer = null;
}
