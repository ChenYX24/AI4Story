import { fetchStories, fetchStory } from "./api.js";
import { state } from "./state.js";
import { initRouter } from "./router.js";
import { toast } from "./toast.js";

export async function mountStoryPicker() {
  const stage = document.getElementById("stage");
  const side = document.getElementById("side");
  if (stage) stage.innerHTML = "";
  if (side) side.innerHTML = "";
  document.getElementById("timeline").innerHTML = "";

  const host = document.createElement("div");
  host.id = "story-picker";
  host.className = "picker";
  host.innerHTML = `
    <div class="picker-head">
      <h1>📖 欢迎来到 AI 故事屋</h1>
      <p>选一本故事，小朋友可以一边看一边改编它 ✨</p>
    </div>
    <div class="picker-grid" id="picker-grid">
      <div class="picker-loading">正在准备故事...</div>
    </div>
  `;
  // mount on top of #app, full bleed
  const app = document.getElementById("app");
  app.style.display = "none";
  document.body.appendChild(host);

  try {
    const resp = await fetchStories();
    state.stories = resp.stories;
    renderPicker(host);
  } catch (e) {
    host.querySelector(".picker-grid").innerHTML = `<div class="picker-loading">加载失败：${e.message}</div>`;
  }
}

function renderPicker(host) {
  const grid = host.querySelector("#picker-grid");
  grid.innerHTML = "";
  state.stories.forEach((s) => {
    const card = document.createElement("div");
    card.className = `story-card ${s.available ? "available" : "locked"}`;
    card.innerHTML = `
      <div class="story-cover" style="${s.cover_url ? `background-image:url(${s.cover_url})` : ''}">
        ${!s.cover_url ? '<div class="cover-placeholder">🌙</div>' : ''}
        ${!s.available ? '<div class="story-lock">🔒 敬请期待</div>' : ''}
      </div>
      <div class="story-meta">
        <div class="story-title">${escapeHtml(s.title)}</div>
        <div class="story-summary">${escapeHtml(s.summary)}</div>
        <div class="story-scenes">${s.scene_count > 0 ? `${s.scene_count} 幕` : ''}</div>
      </div>
    `;
    if (s.available) {
      card.addEventListener("click", () => pickStory(s.id, host));
    }
    grid.appendChild(card);
  });
}

async function pickStory(storyId, host) {
  state.storyId = storyId;
  try {
    state.story = await fetchStory();
    host.remove();
    document.getElementById("app").style.display = "";
    state.stage = "playing";
    initRouter();
  } catch (e) {
    toast(`加载失败：${e.message}`);
  }
}

function escapeHtml(s) {
  return (s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
