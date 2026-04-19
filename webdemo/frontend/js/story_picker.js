import { fetchStories, fetchStory, postCreateCustomStory, deleteCustomStory, patchCustomStory } from "./api.js";
import { state } from "./state.js";
import { initRouter } from "./router.js";
import { toast } from "./toast.js";

const STORY_POLL_MS = 4000;
let pollTimer = null;
let currentPickerView = "landing";

export async function mountStoryPickerAtStories() {
  stopStoryPolling();
  currentPickerView = "stories";
  document.getElementById("story-picker")?.remove();

  const stage = document.getElementById("stage");
  const side = document.getElementById("side");
  if (stage) stage.innerHTML = "";
  if (side) side.innerHTML = "";
  document.getElementById("timeline").innerHTML = "";

  const host = document.createElement("div");
  host.id = "story-picker";
  host.className = "picker picker-stories";

  const app = document.getElementById("app");
  if (app) app.style.display = "none";
  document.body.appendChild(host);

  await showStories(host, { refresh: true });
}

export async function mountStoryPicker() {
  stopStoryPolling();
  currentPickerView = "landing";
  document.getElementById("story-picker")?.remove();

  const stage = document.getElementById("stage");
  const side = document.getElementById("side");
  if (stage) stage.innerHTML = "";
  if (side) side.innerHTML = "";
  document.getElementById("timeline").innerHTML = "";

  const host = document.createElement("div");
  host.id = "story-picker";
  host.className = "picker picker-landing";

  const app = document.getElementById("app");
  if (app) app.style.display = "none";
  document.body.appendChild(host);

  setTopBarVisible(false);
  renderLanding(host);
  void preloadStories();
}

function renderLanding(host) {
  if (!host.isConnected) return;
  currentPickerView = "landing";
  host.className = "picker picker-landing";
  setTopBarVisible(false);
  host.innerHTML = `
    <div class="landing-shell">
      <div class="landing-deco landing-deco--star">✦</div>
      <div class="landing-deco landing-deco--cloud">☁</div>
      <div class="landing-deco landing-deco--cloud-right">☁</div>
      <div class="landing-deco landing-deco--rainbow">🌈</div>
      <div class="landing-badge">✨ AI 绘本创作伙伴</div>
      <div class="landing-hero">
        <h1 class="landing-title">漫秀<span>Mind Show</span></h1>
        <p class="landing-subtitle">把一点点灵感，变成属于你的绘本故事</p>
      </div>

      <section class="landing-card">
        <div class="landing-tabs" role="tablist" aria-label="创作方式">
          <button type="button" class="landing-tab is-disabled" data-mode="douyin">🎬 抖音链接</button>
          <button type="button" class="landing-tab active" data-mode="text">✍️ 文字描述</button>
          <button type="button" class="landing-tab is-disabled" data-mode="voice">🎙️ 语音讲述</button>
        </div>

        <div class="landing-panel active" data-panel="text">
          <p class="landing-panel-copy">写下你脑海里的角色、场景或冒险灵感，漫秀会把它变成一则可体验的绘本故事。</p>
          <input id="landing-story-title" class="landing-title-input" type="text" placeholder="给故事取个名字（选填）" maxlength="32" />
          <textarea id="landing-story-text" class="landing-textarea" rows="3" placeholder="比如：有一只怕黑的小狐狸，为了找回掉进夜空里的画笔，和一群会发光的萤火虫一起穿过森林。"></textarea>
          <div class=”landing-panel-footer”>
            <button type=”button” id=”landing-story-submit” class=”landing-submit”>开始创作 <span aria-hidden=”true”>→</span></button>
            <div class=”landing-hint”>创作过程大约 1 分钟，请保持网络畅通</div>
          </div>
        </div>
      </section>

      <button type="button" id="landing-view-stories" class="landing-link">查看现有故事 <span aria-hidden="true">→</span></button>
    </div>
  `;

  host.querySelectorAll(".landing-tab.is-disabled").forEach((button) => {
    button.addEventListener("click", () => toast("这个入口暂未开放。"));
  });

  const titleInput = host.querySelector("#landing-story-title");
  const textarea = host.querySelector("#landing-story-text");
  const submitBtn = host.querySelector("#landing-story-submit");
  const viewStoriesBtn = host.querySelector("#landing-view-stories");

  textarea?.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      submitBtn?.click();
    }
  });

  submitBtn?.addEventListener("click", async () => {
    if (!textarea) return;
    submitBtn.disabled = true;
    textarea.disabled = true;
    if (titleInput) titleInput.disabled = true;
    try {
      const card = await submitCustomStoryText(textarea.value, titleInput?.value);
      if (!card) return;
      textarea.value = "";
      if (titleInput) titleInput.value = "";
      await showStories(host, { refresh: true });
      toast("自定义故事已经开始在后台生成了。");
    } catch (e) {
      toast(`创建失败：${e.message}`);
    } finally {
      if (host.isConnected && currentPickerView === "landing") {
        submitBtn.disabled = false;
        textarea.disabled = false;
        if (titleInput) titleInput.disabled = false;
      }
    }
  });

  viewStoriesBtn?.addEventListener("click", () => {
    void showStories(host, { refresh: true });
  });
}

async function showStories(host, { refresh = true } = {}) {
  if (!host.isConnected) return;
  currentPickerView = "stories";
  host.className = "picker picker-stories";
  host.innerHTML = `
    <div class="picker-head picker-head--stories">
      <button type="button" class="back-home-btn" id="back-home-btn">← 返回主页</button>
      <h1>查看现有故事</h1>
      <p>选择一个故事开始冒险，也可以继续创建你自己的绘本故事。</p>
    </div>
    <div class="picker-grid" id="picker-grid">
      <div class="picker-loading">正在准备故事卡片...</div>
    </div>
  `;
  setTopBarVisible(true);

  host.querySelector("#back-home-btn")?.addEventListener("click", () => {
    stopStoryPolling();
    renderLanding(host);
  });

  if (state.stories.length) {
    renderPicker(host);
    syncStoryPolling(host);
  }

  if (!refresh) return;
  try {
    await refreshStories(host);
  } catch (e) {
    const grid = host.querySelector("#picker-grid");
    if (grid) {
      grid.innerHTML = `<div class="picker-loading">加载失败：${escapeHtml(e.message)}</div>`;
    }
  }
}

async function preloadStories() {
  try {
    const resp = await fetchStories();
    state.stories = resp.stories;
  } catch (_) {}
}

async function refreshStories(host) {
  const resp = await fetchStories();
  if (!host.isConnected) return;
  state.stories = resp.stories;
  if (currentPickerView === "stories") {
    renderPicker(host);
    syncStoryPolling(host);
  }
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

  const editBtn = story.is_custom && story.available
    ? `<button class="story-edit-btn" title="修改标题">✎</button>`
    : "";

  card.innerHTML = `
    <div class="story-cover ${story.status === "generating" ? "is-generating" : ""}" style="${story.cover_url ? `background-image:url(${story.cover_url})` : ""}">
      ${!story.cover_url ? `<div class="cover-placeholder">${coverFallback}</div>` : ""}
      ${badge}
      ${deleteBtn}
      ${editBtn}
    </div>
    <div class="story-meta">
      <div class="story-title">${escapeHtml(story.title)}</div>
      <div class="story-summary">${escapeHtml(story.summary || "")}</div>
      <div class="story-scenes">${escapeHtml(scenesText)}</div>
      ${progressBar}
    </div>
  `;

  // Red dot: permanently dismiss on hover
  const dot = card.querySelector(".story-new-dot");
  if (dot) {
    card.addEventListener("mouseenter", () => {
      markStorySeen(story.id);
      dot.style.display = "none";
    }, { once: true });
  }

  if (story.available) {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".story-edit-btn")) return;
      pickStory(story.id, host);
    });
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
  // Edit title
  const editBtnEl = card.querySelector(".story-edit-btn");
  if (editBtnEl) {
    editBtnEl.addEventListener("click", (e) => {
      e.stopPropagation();
      openEditTitleModal(story, host);
    });
  }
  return card;
}

function openEditTitleModal(story, host) {
  const modal = document.createElement("div");
  modal.className = "modal";
  modal.innerHTML = `
    <div class="modal-box">
      <h3>修改故事标题</h3>
      <input id="edit-title-input" type="text" value="${escapeHtml(story.title)}" maxlength="32" />
      <div class="modal-actions">
        <button class="secondary" id="edit-title-cancel">取消</button>
        <button id="edit-title-save">保存</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  const input = modal.querySelector("#edit-title-input");
  input.focus();
  input.select();
  modal.querySelector("#edit-title-cancel").onclick = () => modal.remove();
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") modal.querySelector("#edit-title-save").click();
  });
  modal.querySelector("#edit-title-save").onclick = async () => {
    const newTitle = input.value.trim();
    if (!newTitle) { toast("标题不能为空。"); return; }
    try {
      await patchCustomStory(story.id, { title: newTitle });
      const s = state.stories.find((s) => s.id === story.id);
      if (s) s.title = newTitle;
      renderPicker(host);
      modal.remove();
      toast("标题已更新。");
    } catch (err) {
      toast(`更新失败：${err.message}`);
    }
  };
}

const SEEN_STORIES_KEY = "mindshow_seen_stories";

function getSeenStories() {
  try { return new Set(JSON.parse(localStorage.getItem(SEEN_STORIES_KEY) || "[]")); } catch (_) { return new Set(); }
}

function markStorySeen(storyId) {
  const seen = getSeenStories();
  seen.add(storyId);
  localStorage.setItem(SEEN_STORIES_KEY, JSON.stringify([...seen]));
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
  if (story.is_custom && story.available && !getSeenStories().has(story.id)) {
    return `<div class="story-new-dot" data-story-id="${escapeHtml(story.id)}"></div>`;
  }
  return "";
}

function openCreateStoryModal(host) {
  const modal = document.createElement("div");
  modal.className = "modal";
  modal.innerHTML = `
    <div class="modal-box story-input-modal">
      <h3>创建自定义故事</h3>
      <label for="custom-story-title">故事标题</label>
      <input id="custom-story-title" type="text" placeholder="给故事取个名字（选填）" maxlength="32" />
      <label for="custom-story-text">故事文本</label>
      <textarea id="custom-story-text" rows="7" placeholder="比如：在海边的小镇里，有一只想去月亮上画画的小狐狸。它背着画板，和会唱歌的海鸥一起展开冒险......"></textarea>
      <div class="modal-hint">提交后会留在故事列表页，并出现一张“生成中”的故事卡片。</div>
      <div class="modal-actions">
        <button class="secondary" id="custom-story-cancel">取消</button>
        <button id="custom-story-submit">开始生成</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  const modalTitle = modal.querySelector("#custom-story-title");
  const textarea = modal.querySelector("#custom-story-text");
  const submitBtn = modal.querySelector("#custom-story-submit");
  const cancelBtn = modal.querySelector("#custom-story-cancel");
  modalTitle.focus();

  cancelBtn.onclick = () => modal.remove();
  textarea.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      submitBtn.click();
    }
  });
  submitBtn.onclick = async () => {
    submitBtn.disabled = true;
    cancelBtn.disabled = true;
    try {
      const card = await submitCustomStoryText(textarea.value, modalTitle.value);
      if (!card) {
        submitBtn.disabled = false;
        cancelBtn.disabled = false;
        return;
      }
      renderPicker(host);
      syncStoryPolling(host);
      modal.remove();
      toast("自定义故事已经开始在后台生成了。");
      void refreshStories(host).catch(() => {});
    } catch (e) {
      submitBtn.disabled = false;
      cancelBtn.disabled = false;
      toast(`创建失败：${e.message}`);
    }
  };
}

async function submitCustomStoryText(text, title) {
  const normalized = (text || "").trim();
  if (!normalized) {
    toast("先输入一点故事内容吧。");
    return null;
  }
  const payload = { text: normalized };
  if (title && title.trim()) payload.title = title.trim();
  const card = await postCreateCustomStory(payload);
  mergeCustomStoryCard(card);
  return card;
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
    setTopBarVisible(true);
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
    if (!host.isConnected || currentPickerView !== "stories") {
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

function setTopBarVisible(visible) {
  const topBar = document.getElementById("top-bar");
  if (!topBar) return;
  topBar.classList.toggle("top-bar-hidden", !visible);
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
