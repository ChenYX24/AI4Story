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
  st.classList.add("fading");
  stopTTS();
  await new Promise((r) => setTimeout(r, 380));

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
