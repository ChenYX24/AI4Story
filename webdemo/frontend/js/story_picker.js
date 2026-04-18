import { fetchStories, fetchStory, postCreateCustomStory, deleteCustomStory } from "./api.js";
import { state } from "./state.js";
import { initRouter } from "./router.js";
import { toast } from "./toast.js";

const STORY_POLL_MS = 4000;
let pollTimer = null;

export async function mountStoryPicker() {
  stopStoryPolling();
  document.getElementById("story-picker")?.remove();

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
      <h1>欢迎来到 AI 故事屋</h1>
      <p>选择一个故事开始冒险，也可以把你自己的故事变成一整本可玩的绘本。</p>
    </div>
    <div class="picker-grid" id="picker-grid">
      <div class="picker-loading">正在准备故事卡片...</div>
    </div>
  `;

  const app = document.getElementById("app");
  app.style.display = "none";
  document.body.appendChild(host);

  try {
    await refreshStories(host);
  } catch (e) {
    const grid = host.querySelector(".picker-grid");
    if (grid) {
      grid.innerHTML = `<div class="picker-loading">加载失败：${escapeHtml(e.message)}</div>`;
    }
  }
}

async function refreshStories(host) {
  const resp = await fetchStories();
  if (!host.isConnected) return;
  state.stories = resp.stories;
  renderPicker(host);
  syncStoryPolling(host);
}

function renderPicker(host) {
  const grid = host.querySelector("#picker-grid");
  if (!grid) return;
  grid.innerHTML = "";
  grid.appendChild(buildCreateStoryCard(host));
  state.stories.forEach((story) => grid.appendChild(buildStoryCard(story, host)));
}

function buildCreateStoryCard(host) {
  const card = document.createElement("div");
  card.className = "story-card available custom-entry";
  card.innerHTML = `
    <div class="story-cover entry-cover">
      <div class="entry-icon">✏️</div>
      <div class="story-badge entry">自定义</div>
    </div>
    <div class="story-meta">
      <div class="story-title">创建你的故事</div>
      <div class="story-summary">输入一段你想讲的故事，系统会在后台自动拆分章节、生成角色和场景，完成后就能像其他故事一样进入体验。</div>
      <div class="story-scenes">点击开始输入</div>
    </div>
  `;
  card.addEventListener("click", () => openCreateStoryModal(host));
  return card;
}

function buildStoryCard(story, host) {
  const card = document.createElement("div");
  const cardStateClass = story.available
    ? "available"
    : story.status === "generating"
      ? "pending"
      : story.status === "failed"
        ? "failed"
        : "locked";
  card.className = `story-card ${cardStateClass}`;

  const coverFallback = story.status === "generating"
    ? "⏳"
    : story.status === "failed"
      ? "⚠️"
      : story.is_custom
        ? "📘"
        : "📖";
  const badge = renderStoryBadge(story);
  const scenesText = story.scene_count > 0
    ? `${story.scene_count} 幕`
    : story.status === "generating"
      ? "后台生成中"
      : story.status === "failed"
        ? "生成失败"
        : "";

  const progressBar = story.status === "generating"
    ? `<div class="story-progress">
        <div class="story-progress-bar" style="width:${story.progress || 0}%"></div>
       </div>
       <div class="story-progress-label">${escapeHtml(story.progress_label || "生成中")}</div>`
    : "";

  const deleteBtn = story.status === "failed" && story.is_custom
    ? `<button class="story-delete-btn" title="删除此故事">✕</button>`
    : "";

  card.innerHTML = `
    <div class="story-cover ${story.status === "generating" ? "is-generating" : ""}" style="${story.cover_url ? `background-image:url(${story.cover_url})` : ""}">
      ${!story.cover_url ? `<div class="cover-placeholder">${coverFallback}</div>` : ""}
      ${badge}
      ${deleteBtn}
    </div>
    <div class="story-meta">
      <div class="story-title">${escapeHtml(story.title)}</div>
      <div class="story-summary">${escapeHtml(story.summary || "")}</div>
      <div class="story-scenes">${escapeHtml(scenesText)}</div>
      ${progressBar}
    </div>
  `;

  if (story.available) {
    card.addEventListener("click", () => pickStory(story.id, host));
  } else if (story.status === "failed") {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".story-delete-btn")) return;
      toast(story.error_message || "这个自定义故事生成失败了，请重新创建一个。");
    });
    const btn = card.querySelector(".story-delete-btn");
    if (btn) {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await deleteCustomStory(story.id);
          state.stories = state.stories.filter((s) => s.id !== story.id);
          renderPicker(host);
        } catch (err) {
          toast(`删除失败：${err.message}`);
        }
      });
    }
  }
  return card;
}

function renderStoryBadge(story) {
  if (story.status === "generating") {
    return `<div class="story-badge generating"><span class="badge-spinner"></span>生成中</div>`;
  }
  if (story.status === "failed") {
    return `<div class="story-badge failed">生成失败</div>`;
  }
  if (story.status === "locked") {
    return `<div class="story-badge locked">敬请期待</div>`;
  }
  if (story.is_custom) {
    return `<div class="story-badge ready">已生成</div>`;
  }
  return "";
}

function openCreateStoryModal(host) {
  const modal = document.createElement("div");
  modal.className = "modal";
  modal.innerHTML = `
    <div class="modal-box story-input-modal">
      <h3>创建自定义故事</h3>
      <label for="custom-story-text">故事文本</label>
      <textarea id="custom-story-text" rows="7" placeholder="比如：在海边的小镇里，有一只想去月亮上画画的小狐狸。它背着画板，和会唱歌的海鸥一起展开冒险......"></textarea>
      <div class="modal-hint">提交后会立即回到首页，并出现一张“生成中”的故事卡片。生成期间你可以继续进入其他故事。</div>
      <div class="modal-actions">
        <button class="secondary" id="custom-story-cancel">取消</button>
        <button id="custom-story-submit">开始生成</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  const textarea = modal.querySelector("#custom-story-text");
  const submitBtn = modal.querySelector("#custom-story-submit");
  const cancelBtn = modal.querySelector("#custom-story-cancel");
  textarea.focus();

  cancelBtn.onclick = () => modal.remove();
  textarea.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      submitBtn.click();
    }
  });
  submitBtn.onclick = async () => {
    const text = (textarea.value || "").trim();
    if (!text) {
      toast("先输入一点故事内容吧。");
      return;
    }
    submitBtn.disabled = true;
    cancelBtn.disabled = true;
    try {
      const card = await postCreateCustomStory({ text });
      mergeCustomStoryCard(card);
      renderPicker(host);
      syncStoryPolling(host);
      modal.remove();
      toast("自定义故事已经开始在后台生成了。");
    } catch (e) {
      submitBtn.disabled = false;
      cancelBtn.disabled = false;
      toast(`创建失败：${e.message}`);
    }
  };
}

function mergeCustomStoryCard(card) {
  const nextStories = state.stories.filter((item) => item.id !== card.id);
  const defaultIndex = nextStories.findIndex((item) => item.id === "little_red_riding_hood");
  const insertIndex = defaultIndex >= 0 ? defaultIndex + 1 : 0;
  nextStories.splice(insertIndex, 0, card);
  state.stories = nextStories;
}

async function pickStory(storyId, host) {
  stopStoryPolling();
  try {
    const story = await fetchStory(storyId);
    state.storyId = storyId;
    state.story = story;
    host.remove();
    document.getElementById("app").style.display = "";
    state.stage = "playing";
    initRouter();
  } catch (e) {
    toast(`加载失败：${e.message}`);
  }
}

function syncStoryPolling(host) {
  const hasGeneratingStory = state.stories.some((story) => story.status === "generating");
  if (hasGeneratingStory) {
    startStoryPolling(host);
  } else {
    stopStoryPolling();
  }
}

function startStoryPolling(host) {
  if (pollTimer) return;
  pollTimer = window.setInterval(async () => {
    if (!host.isConnected) {
      stopStoryPolling();
      return;
    }
    try {
      await refreshStories(host);
    } catch (e) {
      console.warn("story poll failed:", e);
    }
  }, STORY_POLL_MS);
}

function stopStoryPolling() {
  if (!pollTimer) return;
  window.clearInterval(pollTimer);
  pollTimer = null;
}

function escapeHtml(s) {
  return (s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}
