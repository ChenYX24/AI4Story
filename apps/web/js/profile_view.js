// F1 骨架：localStorage 假登录 + 三 tab 个人页（stories / sessions / assets）
// 真正的账户 + DB schema 在阶段 2 后半段落地（见 ADR-002）。
import { toast } from "./toast.js";

const USER_KEY = "mindshow_user";
const ASSETS_KEY = "mindshow_my_assets";
const SESSIONS_KEY = "mindshow_my_sessions";
const STORIES_KEY = "mindshow_my_stories";

// ---- 简易 store ----
function getUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; }
}
function setUser(u) { localStorage.setItem(USER_KEY, JSON.stringify(u)); }
function clearUser() { localStorage.removeItem(USER_KEY); }

function readJson(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || "null") || fallback; } catch { return fallback; }
}

// ---- UI ----
export function openProfile() {
  const user = getUser();
  if (!user) {
    showLoginModal();
    return;
  }
  renderProfile(user);
}

function showLoginModal() {
  const m = document.createElement("div");
  m.className = "profile-login-modal";
  m.innerHTML = `
    <div class="profile-login-box">
      <h3>👋 欢迎来到漫秀</h3>
      <p>先取个昵称，后续资产、会话、报告都会记到你的账户下。</p>
      <input id="pl-nick" type="text" placeholder="小朋友的昵称，例如：糖糖" maxlength="20" />
      <button id="pl-ok">开始</button>
      <div style="margin-top:10px;font-size:12px;color:#b39a7a">MVP 阶段：仅本地记录；阶段 2 接入真正账户</div>
    </div>
  `;
  document.body.appendChild(m);
  const input = m.querySelector("#pl-nick");
  input.focus();
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") m.querySelector("#pl-ok").click(); });
  m.querySelector("#pl-ok").onclick = () => {
    const nick = (input.value || "").trim();
    if (!nick) { toast("请输入昵称"); return; }
    const id = "u_" + Math.random().toString(36).slice(2, 10);
    const created_at = new Date().toISOString();
    setUser({ id, nick, created_at });
    m.remove();
    renderProfile({ id, nick, created_at });
  };
}

function renderProfile(user) {
  let host = document.getElementById("profile-root");
  if (host) host.remove();
  host = document.createElement("div");
  host.id = "profile-root";
  host.className = "profile-root";
  const avatar = user.nick.slice(0, 1).toUpperCase();

  host.innerHTML = `
    <div class="profile-head">
      <div class="profile-avatar">${escapeHtml(avatar)}</div>
      <div class="profile-name-row">
        <div class="profile-nick">${escapeHtml(user.nick)}</div>
        <div class="profile-sub">加入于 ${new Date(user.created_at).toLocaleDateString()}</div>
      </div>
      <button class="profile-logout" id="p-logout" title="清除本地昵称">登出</button>
      <button class="profile-close" id="p-close" title="关闭">✕</button>
    </div>

    <div class="profile-tabs">
      <button class="profile-tab active" data-tab="stories">📖 我的故事</button>
      <button class="profile-tab" data-tab="sessions">🎮 历史会话</button>
      <button class="profile-tab" data-tab="assets">🎨 资产</button>
    </div>

    <div class="profile-body" id="profile-body"></div>
  `;

  document.body.appendChild(host);

  host.querySelector("#p-logout").onclick = () => {
    clearUser();
    host.remove();
    toast("已登出");
  };
  host.querySelector("#p-close").onclick = () => host.remove();
  host.querySelectorAll(".profile-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      host.querySelectorAll(".profile-tab").forEach((x) => x.classList.toggle("active", x === btn));
      renderTab(host, btn.dataset.tab, user);
    });
  });

  renderTab(host, "stories", user);
}

function renderTab(host, tab, user) {
  const body = host.querySelector("#profile-body");
  if (!body) return;
  if (tab === "stories") return renderStories(body, user);
  if (tab === "sessions") return renderSessions(body, user);
  if (tab === "assets") return renderAssets(body, user);
}

function renderStories(body, user) {
  const stories = readJson(STORIES_KEY, []);
  if (!stories.length) {
    body.innerHTML = emptyBlock("📖", "还没有创建过故事", "去首页输入一段描述，或用视频 / 音频 / 手绘创建故事。");
    return;
  }
  body.innerHTML = `<div class="profile-grid">${stories.map(storyCard).join("")}</div>`;
}

function renderSessions(body, user) {
  const sessions = readJson(SESSIONS_KEY, []);
  if (!sessions.length) {
    body.innerHTML = emptyBlock("🎮", "还没有玩过的会话", "玩完一遍故事后，这里会按故事归档每次的记录和报告。");
    return;
  }
  // 按 story 分组
  const byStory = {};
  sessions.forEach((s) => {
    const k = s.story_title || "未命名故事";
    (byStory[k] ??= []).push(s);
  });
  const groups = Object.entries(byStory).map(([title, list]) => `
    <div style="margin-bottom:20px">
      <div style="font-weight:700;color:#3a2515;margin:8px 2px;">${escapeHtml(title)} · ${list.length} 次</div>
      <div class="profile-grid">
        ${list.map(sessionCard).join("")}
      </div>
    </div>
  `).join("");
  body.innerHTML = groups;
}

function renderAssets(body, user) {
  let sub = body.dataset.sub || "mine";
  body.innerHTML = `
    <div class="profile-subtabs" id="asset-subs">
      <button class="profile-subtab ${sub === "mine" ? "active" : ""}" data-sub="mine">我生成的</button>
      <button class="profile-subtab ${sub === "imported" ? "active" : ""}" data-sub="imported">导入的</button>
      <button class="profile-subtab ${sub === "official" ? "active" : ""}" data-sub="official">官方共享库</button>
    </div>
    <div class="asset-actions">
      <button class="asset-action-btn" id="asset-import-btn">＋ 输入分享码导入</button>
      <button class="asset-action-btn" id="asset-pack-btn">📦 打包分享（多选）</button>
    </div>
    <div id="asset-grid"></div>
  `;
  body.querySelector("#asset-import-btn").onclick = () => toast("分享码导入：阶段 2 打通真正后端 CRUD 后可用。");
  body.querySelector("#asset-pack-btn").onclick = () => toast("多选打包分享：阶段 2 可用。");
  body.querySelectorAll(".profile-subtab").forEach((btn) => {
    btn.addEventListener("click", () => {
      body.dataset.sub = btn.dataset.sub;
      renderAssets(body, user);
    });
  });
  renderAssetGrid(body.querySelector("#asset-grid"), sub);
}

function renderAssetGrid(grid, sub) {
  if (sub === "official") {
    grid.innerHTML = `
      <div class="profile-grid">
        ${mockOfficialAssets().map(assetCard).join("")}
      </div>`;
    return;
  }
  if (sub === "imported") {
    grid.innerHTML = emptyBlock("📥", "还没有导入的资产", "让朋友给你一个分享码，粘贴后就能把他们的角色/道具加到你的库里。");
    return;
  }
  const mine = readJson(ASSETS_KEY, []);
  if (!mine.length) {
    grid.innerHTML = emptyBlock("🎨", "还没有生成过资产", "每次创作都会自动把新角色和道具存进来。");
    return;
  }
  grid.innerHTML = `<div class="profile-grid">${mine.map(assetCard).join("")}</div>`;
}

// ---- card builders ----
function storyCard(s) {
  return `
    <div class="profile-card">
      <div class="pc-cover">${escapeHtml(s.cover || "📖")}</div>
      <div class="pc-title">${escapeHtml(s.title || "未命名故事")}</div>
      <div class="pc-meta">${escapeHtml(s.scene_count || 0)} 幕 · ${escapeHtml(s.created_at ? new Date(s.created_at).toLocaleDateString() : "")}</div>
    </div>
  `;
}

function sessionCard(s) {
  return `
    <div class="profile-card">
      <div class="pc-cover">🎬</div>
      <div class="pc-title">${escapeHtml(s.started_at ? new Date(s.started_at).toLocaleString() : "一次会话")}</div>
      <div class="pc-meta">${s.report_ready ? "✓ 报告已生成" : "进行中"}</div>
    </div>
  `;
}

function assetCard(a) {
  return `
    <div class="profile-card">
      <div class="pc-cover">${escapeHtml(a.cover || "🎭")}</div>
      <div class="pc-title">${escapeHtml(a.name || "未命名资产")}</div>
      <div class="pc-meta">${escapeHtml(a.kind || "")} ${a.source === "official" ? "· 官方" : ""}</div>
    </div>
  `;
}

function emptyBlock(icon, title, hint, { backHome = true } = {}) {
  const btn = backHome
    ? `<button class="pe-action" data-action="home">返回首页创作 →</button>`
    : "";
  return `
    <div class="profile-empty">
      <div class="pe-icon">${icon}</div>
      <div style="font-weight:700;color:#3a2515;margin-bottom:4px;">${escapeHtml(title)}</div>
      <div style="font-size:13px;">${escapeHtml(hint)}</div>
      ${btn}
    </div>
  `;
}

// 委托：profile-empty 内的 "返回首页创作" 按钮统一处理
document.addEventListener("click", (e) => {
  const btn = e.target.closest?.(".pe-action[data-action='home']");
  if (!btn) return;
  const root = document.getElementById("profile-root");
  if (root) root.remove();
});

function mockOfficialAssets() {
  return [
    { name: "经典童话角色包", cover: "🎭", kind: "人物", source: "official" },
    { name: "魔法道具 × 20", cover: "🗝️", kind: "道具", source: "official" },
    { name: "森林 / 城堡 / 海底背景", cover: "🌲", kind: "背景", source: "official" },
    { name: "节日场景包", cover: "🎉", kind: "场景", source: "official" },
  ];
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
