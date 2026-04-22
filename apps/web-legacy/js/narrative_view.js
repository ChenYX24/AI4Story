import { playTTS, preloadTTS, stopTTS } from "./tts.js";
import { listenOnce, asrSupported } from "./asr.js";
import { postChat } from "./api.js";
import { state } from "./state.js";
import { toast } from "./toast.js";
import { goToNode } from "./router.js";
import { showReport } from "./report_view.js";

let cursor = 0;
let data = null; // { source, scene? | payload?, title, sceneIdx? }
let preloadedAudios = []; // [{ promise: Promise<ctrl | null> }]

/**
 * Accepts either:
 *   { source: "fixed", scene: {...fetch /api/scene/{idx}...} }
 *   { source: "dynamic", payload: {...interact response...} }
 */
export function mountNarrative(arg) {
  const { source, scene, payload } = arg;
  const title = source === "dynamic" ? "✨ 新的故事段落" : `第 ${scene.index} 幕 · 叙事`;
  const comic = source === "dynamic" ? payload.comic_url : scene.comic_url;
  const summary = source === "dynamic" ? payload.summary : (scene.summary || scene.narration || "");
  const storyboard = source === "dynamic" ? payload.storyboard : scene.storyboard;

  data = { source, scene, payload, title, storyboard, sceneIdx: scene?.index };
  cursor = 0;
  // Pre-load all TTS audio in parallel so playback starts instantly on click
  preloadedAudios = (storyboard || []).map((line) => ({
    promise: preloadTTS(line.text, { tone: line.tone, speaker: line.speaker }).catch((e) => {
      console.warn("tts preload:", e.message);
      return null;
    }),
  }));

  const stage = document.getElementById("stage");
  stage.innerHTML = `
    <div class="book-wrap flip-in">
      <div class="book-page">
        <div class="comic-wrap">
          <img class="comic-img" src="${comic}" alt="连环画" />
        </div>
        <div class="comic-controls">
          <button class="secondary" id="btn-prev">⬅ 上一页</button>
          <button id="btn-replay">🔊 重播</button>
          <button id="btn-next-line">下一句 ▶</button>
          <button id="btn-next-scene">翻下一页 ⏭</button>
        </div>
      </div>
    </div>
  `;
  // clean up the flip-in class after animation so subsequent flips work
  const book = stage.querySelector(".book-wrap");
  if (book) setTimeout(() => book.classList.remove("flip-in"), 750);

  const side = document.getElementById("side");
  side.innerHTML = `
    <h2>${title}</h2>
    <div class="summary">${escapeHtml(summary)}</div>
    <div class="story-log" id="story-log"></div>
    <div class="line-pending" id="line-pending"><span>·</span><span>·</span><span>·</span> 准备朗读</div>
    <div class="chat-row">
      <input type="text" id="chat-input" placeholder="小朋友想说点什么？" />
      <button class="mic" id="chat-mic" ${asrSupported() ? "" : "disabled"}>🎤</button>
      <button id="chat-send">发送</button>
    </div>
  `;

  document.getElementById("btn-prev").onclick = () => goToNode(state.cursor - 1);
  document.getElementById("btn-next-scene").onclick = () => {
    const next = state.cursor + 1;
    if (next >= state.flow.length) {
      // last scene — offer the report
      showReport();
      return;
    }
    state.highestUnlocked = Math.max(state.highestUnlocked, next);
    goToNode(next);
  };
  // relabel on last scene
  if (state.cursor === state.flow.length - 1) {
    const btn = document.getElementById("btn-next-scene");
    if (btn) btn.textContent = "📊 查看报告";
  }
  document.getElementById("btn-next-line").onclick = () => advanceLine();
  document.getElementById("btn-replay").onclick = () => replayLine();

  const input = document.getElementById("chat-input");
  document.getElementById("chat-send").onclick = () => sendChat(input.value);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendChat(input.value);
  });
  document.getElementById("chat-mic").onclick = () => startMic();

  setTimeout(() => advanceLine(), 300);
}

export function unmountNarrative() {
  stopTTS();
  // dispose pre-loaded blobs
  preloadedAudios.forEach(async (slot) => {
    try { const c = await slot.promise; c?.stop?.(); } catch (_) {}
  });
  preloadedAudios = [];
  data = null;
  cursor = 0;
}

let advancing = false;
async function advanceLine() {
  if (!data || advancing) return;
  const lines = data.storyboard || [];
  if (cursor >= lines.length) {
    toast("这一幕讲完啦，点「进入下一幕」吧！");
    return;
  }
  const idx = cursor;
  const line = lines[idx];
  cursor += 1;
  advancing = true;
  setLinePending(true);
  let ctrl = null;
  const slot = preloadedAudios[idx];
  if (slot) {
    ctrl = await slot.promise;
  }
  // sync point: bubble + audio start together
  setLinePending(false);
  appendLog(line.kind, line.speaker, line.text);
  advancing = false;
  if (ctrl) {
    await ctrl.play();
  }
}

function setLinePending(on) {
  const btn = document.getElementById("btn-next-line");
  const dot = document.getElementById("line-pending");
  if (btn) btn.disabled = on;
  if (dot) dot.classList.toggle("show", on);
}

function replayLine() {
  if (!data || cursor === 0) return;
  const line = data.storyboard[cursor - 1];
  playTTS(line.text, { tone: line.tone, speaker: line.speaker });
}

function appendLog(kind, speaker, text) {
  const log = document.getElementById("story-log");
  const b = document.createElement("div");
  b.className = `bubble ${kind}`;
  b.innerHTML = `<div class="speaker">${escapeHtml(speaker)}</div>${escapeHtml(text)}`;
  log.appendChild(b);
  log.scrollTop = log.scrollHeight;
}

async function sendChat(text) {
  const v = (text || "").trim();
  if (!v) return;
  const input = document.getElementById("chat-input");
  if (input) input.value = "";
  appendUserBubble(v);
  try {
    const resp = await postChat({ scene_idx: data.sceneIdx || 0, user_text: v });
    let ctrl = null;
    try { ctrl = await preloadTTS(resp.reply, { tone: "温柔" }); } catch (_) {}
    appendLog("assistant", "讲故事的人", resp.reply);
    if (ctrl) ctrl.play();
  } catch (e) {
    toast(`出错了：${e.message}`);
  }
}

function appendUserBubble(text) {
  const log = document.getElementById("story-log");
  const b = document.createElement("div");
  b.className = "bubble user";
  b.innerHTML = `<div class="speaker">我</div>${escapeHtml(text)}`;
  log.appendChild(b);
  log.scrollTop = log.scrollHeight;
}

async function startMic() {
  const btn = document.getElementById("chat-mic");
  if (!asrSupported()) {
    toast("浏览器不支持语音识别，建议使用 Chrome 或直接输入");
    return;
  }
  btn.classList.add("listening");
  try {
    const text = await listenOnce({ lang: "zh-CN" });
    btn.classList.remove("listening");
    const input = document.getElementById("chat-input");
    if (input) input.value = text;
    sendChat(text);
  } catch (e) {
    btn.classList.remove("listening");
    toast(`没听清：${e.message}`);
  }
}

function escapeHtml(s) {
  return (s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
