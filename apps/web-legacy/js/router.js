import { fetchScene } from "./api.js";
import { state, clearInteractive, buildInitialFlow } from "./state.js";
import { mountNarrative, unmountNarrative } from "./narrative_view.js";
import { mountInteractive, unmountInteractive } from "./interactive_view.js";
import { stopTTS } from "./tts.js";
import { toast } from "./toast.js";
import { renderTimeline } from "./timeline.js";

const stage = () => document.getElementById("stage");
const side = () => document.getElementById("side");
let currentType = null;

function prefetchNode(idx) {
  if (idx < 0 || idx >= state.flow.length) return;
  const node = state.flow[idx];
  if (!node.sceneIdx) return;
  fetchScene(node.sceneIdx).then((scene) => {
    const urls = [];
    if (scene.comic_url) urls.push(scene.comic_url);
    if (scene.background_url) urls.push(scene.background_url);
    (scene.characters || []).forEach((c) => c.url && urls.push(c.url));
    (scene.props || []).forEach((p) => p.url && urls.push(p.url));
    urls.forEach((u) => { const img = new Image(); img.src = u; });
  }).catch(() => {});
}

function unmountCurrent() {
  if (currentType === "narrative") unmountNarrative();
  else if (currentType === "interactive") unmountInteractive();
  stage().innerHTML = "";
  side().innerHTML = "";
  currentType = null;
}

export async function goToNode(idx) {
  if (idx < 0 || idx >= state.flow.length) return;
  if (idx > state.highestUnlocked) {
    toast("还没解锁哦～");
    return;
  }
  const st = stage();
  // 书本翻页方向：点"下一幕" = 正向翻，"上一幕" = 反向翻
  const direction = idx >= (state.cursor ?? 0) ? "next" : "prev";
  const existingBook = st.querySelector(".book-wrap");
  if (existingBook) {
    existingBook.classList.add(direction === "next" ? "flip-next" : "flip-prev");
  } else {
    st.classList.add("fading");
  }
  stopTTS();
  // 翻页动画时长 ≈ 700ms，其间发网络请求同时进行，DOM 替换在最后
  await new Promise((r) => setTimeout(r, existingBook ? 560 : 380));

  const node = state.flow[idx];
  try {
    clearInteractive();
    unmountCurrent();

    if (node.source === "dynamic" && node.kind === "narrative") {
      mountNarrative({ source: "dynamic", payload: node.payload });
      currentType = "narrative";
    } else if (node.kind === "narrative") {
      const scene = await fetchScene(node.sceneIdx);
      mountNarrative({ source: "fixed", scene });
      currentType = "narrative";
    } else {
      const scene = await fetchScene(node.sceneIdx);
      mountInteractive(scene);
      currentType = "interactive";
    }

    state.cursor = idx;
    state.highestUnlocked = Math.max(state.highestUnlocked, idx);
    node.visited = true;
    renderTimeline();
    prefetchNode(idx + 1);
  } catch (e) {
    toast(`加载失败：${e.message}`);
    console.error(e);
  } finally {
    st.classList.remove("fading");
  }
}

export function initRouter() {
  state.flow = buildInitialFlow(state.story);
  state.cursor = 0;
  state.highestUnlocked = 0;
  renderTimeline();
  goToNode(0);
}
