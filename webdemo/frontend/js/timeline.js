import { state } from "./state.js";
import { goToNode } from "./router.js";
import { toast } from "./toast.js";

export function renderTimeline() {
  const el = document.getElementById("timeline");
  if (!el) return;
  el.innerHTML = "";
  state.flow.forEach((node, idx) => {
    const item = document.createElement("div");
    const isLocked = idx > state.highestUnlocked;
    const isCurrent = idx === state.cursor;
    item.className = [
      "tl-node",
      node.kind,
      node.source,
      isLocked ? "locked" : node.visited ? "visited" : "unlocked",
      isCurrent ? "current" : "",
    ].join(" ").trim();
    item.title = node.title || "";

    const thumb = document.createElement("div");
    thumb.className = "tl-thumb";
    if (node.thumbnail) {
      thumb.style.backgroundImage = `url(${node.thumbnail})`;
    } else if (node.source === "fixed" && node.kind === "narrative") {
      thumb.style.backgroundImage = `url(/assets/scenes/${String(node.sceneIdx).padStart(3, "0")}/comic/panel.png)`;
    } else if (node.source === "fixed" && node.kind === "interactive") {
      thumb.style.backgroundImage = `url(/assets/scenes/${String(node.sceneIdx).padStart(3, "0")}/background/background.png)`;
    }
    item.appendChild(thumb);

    const label = document.createElement("div");
    label.className = "tl-label";
    label.textContent = nodeLabel(node, idx);
    item.appendChild(label);

    if (node.source === "dynamic") {
      const tag = document.createElement("span");
      tag.className = "tl-tag";
      tag.textContent = "✨";
      item.appendChild(tag);
    }

    item.addEventListener("click", () => {
      if (isLocked) {
        toast("这一幕还没解锁呢，先完成当前的故事吧～");
        return;
      }
      if (idx === state.cursor) return;
      goToNode(idx);
    });

    el.appendChild(item);
  });
  // scroll current into view
  const cur = el.querySelector(".tl-node.current");
  cur?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
}

function nodeLabel(node, idx) {
  if (node.source === "dynamic") return "✨新段落";
  const prefix = node.kind === "interactive" ? "交互" : "叙事";
  return `${prefix} · ${node.sceneIdx ?? idx + 1}`;
}
