import { postReport } from "./api.js";
import { state } from "./state.js";
import { showLoader, hideLoader, startHintRotation, stopHintRotation, toast } from "./toast.js";
import { stopTTS } from "./tts.js";

export async function showReport() {
  stopTTS();
  state.stage = "report";
  const stage = document.getElementById("stage");
  const side = document.getElementById("side");
  stage.innerHTML = `<div class="report-loading">正在为你整理这场旅程...</div>`;
  side.innerHTML = "";

  showLoader("AI 正在整理报告…");
  startHintRotation();
  try {
    const resp = await postReport({
      session_id: state.sessionId,
      story_id: state.storyId || "little_red_riding_hood",
      interactions: state.storyLog.interactions,
    });
    renderShare(resp);
  } catch (e) {
    stage.innerHTML = `<div class="report-loading error">报告生成失败：${escapeHtml(e.message)}</div>`;
    toast("报告生成失败，稍后再试");
  } finally {
    stopHintRotation();
    hideLoader();
  }
}

function renderShare(data) {
  const stage = document.getElementById("stage");
  const side = document.getElementById("side");
  side.innerHTML = "";

  const share = data.share || {};
  const achievements = share.achievements || [];
  const seed = `${state.sessionId}-${state.storyId || ""}`;

  stage.innerHTML = `
    <div class="share-view">
      <div class="share-confetti"></div>
      <div class="share-honor">
        <div class="trophy">🏆</div>
        <div class="honor-title">${escapeHtml(share.honor_title || "故事小主人")}</div>
        <div class="share-summary">${escapeHtml(share.summary || "")}</div>
      </div>
      <div class="achievements-grid">
        ${achievements.map((a) => `
          <div class="achv-card">
            <div class="achv-icon">${escapeHtml(a.icon || "⭐")}</div>
            <div class="achv-text">${escapeHtml(a.text || "")}</div>
          </div>
        `).join("")}
      </div>
      <div class="share-qr-wrap">
        <div class="share-qr">${fakeQrSvg(seed)}</div>
        <div class="share-qr-hint">扫码分享这本故事书<br><span>（占位，暂未启用）</span></div>
      </div>
      <div class="share-actions">
        <button class="secondary" id="share-back">返回故事</button>
        <button id="share-see-report">查看详细报告 →</button>
      </div>
    </div>
  `;

  document.getElementById("share-back").onclick = () => {
    state.stage = "playing";
    import("./router.js").then((m) => m.goToNode(state.cursor));
  };
  document.getElementById("share-see-report").onclick = () => renderReport(data);
}

function renderReport(data) {
  const stage = document.getElementById("stage");
  const side = document.getElementById("side");
  side.innerHTML = "";
  const kid = data.kid_section || {};
  const parent = data.parent_section || {};
  const metrics = parent.metrics || [];

  stage.innerHTML = `
    <div class="report">
      <div class="report-tabs">
        <button class="report-tab active" data-tab="kid">🧒 给你的报告</button>
        <button class="report-tab" data-tab="parent">👨‍👩‍👧 给家长</button>
      </div>
      <div class="report-body">
        <section class="report-panel kid-panel active" data-tab="kid">
          <h2>${escapeHtml(kid.title || "给你的故事报告")}</h2>
          <div class="report-card">
            <h3>🌟 你创造的故事</h3>
            <p>${escapeHtml(kid.your_story || "")}</p>
          </div>
          <div class="report-card">
            <h3>📖 真实的《小红帽》</h3>
            <p>${escapeHtml(kid.original_story || "")}</p>
          </div>
          <div class="report-card">
            <h3>🔍 你的故事和原著有什么不同？</h3>
            <ul>${(kid.differences || []).map((d) => `<li>${escapeHtml(d)}</li>`).join("")}</ul>
          </div>
          <div class="report-card">
            <h3>💭 思考一下</h3>
            <ol>${(kid.questions || []).map((q) => `<li>${escapeHtml(q)}</li>`).join("")}</ol>
          </div>
        </section>
        <section class="report-panel parent-panel" data-tab="parent">
          <h2>${escapeHtml(parent.title || "给家长看的观察报告")}</h2>
          <div class="report-card">
            <h3>📊 能力维度画像</h3>
            <div class="metric-list">
              ${metrics.map((m) => renderMetricBar(m)).join("")}
            </div>
          </div>
          <div class="report-card">
            <h3>🧩 性格/行为亮点</h3>
            <ul>${(parent.traits || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>
          </div>
          <div class="report-card weak">
            <h3>💡 可以加强的地方</h3>
            <ul>${(parent.weaknesses || []).map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>
          </div>
          <div class="report-card">
            <h3>📝 具体的行为观察</h3>
            <ul>${(parent.observations || []).map((o) => `<li>${escapeHtml(o)}</li>`).join("")}</ul>
          </div>
          <div class="report-card">
            <h3>🌱 教育建议</h3>
            <ol>${(parent.suggestions || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>
          </div>
        </section>
      </div>
      <div class="report-footer">
        <button class="secondary" id="report-back-share">← 回到分享页</button>
        <button class="secondary" id="report-back">返回故事</button>
        <button id="report-restart">🔁 再玩一遍</button>
      </div>
    </div>
  `;
  stage.querySelectorAll(".report-tab").forEach((b) => {
    b.addEventListener("click", () => {
      const t = b.dataset.tab;
      stage.querySelectorAll(".report-tab").forEach((x) => x.classList.toggle("active", x.dataset.tab === t));
      stage.querySelectorAll(".report-panel").forEach((x) => x.classList.toggle("active", x.dataset.tab === t));
    });
  });
  document.getElementById("report-back-share").onclick = () => renderShare(data);
  document.getElementById("report-back").onclick = () => {
    state.stage = "playing";
    import("./router.js").then((m) => m.goToNode(state.cursor));
  };
  document.getElementById("report-restart").onclick = () => {
    window.location.reload();
  };
}

function renderMetricBar(m) {
  const val = Math.max(10, Math.min(95, Number(m.value) || 60));
  const color = val >= 80 ? "#5bbf82" : val >= 60 ? "#ff8a5b" : "#c79b68";
  const evidence = m.evidence || m.description || "";
  // highlight 【...】 references as chips so evidence stands out
  const evidenceHtml = escapeHtml(evidence).replace(
    /【(.+?)】/g,
    '<span class="ev-ref">$1</span>'
  );
  return `
    <div class="metric-row">
      <div class="metric-head">
        <span class="metric-name">${escapeHtml(m.name || "")}</span>
        <span class="metric-val" style="color:${color}">${val}%</span>
      </div>
      <div class="metric-bar">
        <div class="metric-fill" style="width:${val}%; background:${color}"></div>
      </div>
      ${evidence ? `<div class="metric-desc"><span class="ev-label">依据</span>${evidenceHtml}</div>` : ""}
    </div>
  `;
}

// ---- fake QR placeholder ----
// Deterministic 25x25 SVG with finder squares. Seed drives middle pattern.
function fakeQrSvg(seed) {
  const N = 25;
  const cell = 10;
  const size = N * cell;
  const s = hashSeed(seed);
  const rng = mulberry32(s);
  const bits = [];
  for (let y = 0; y < N; y++) {
    bits.push([]);
    for (let x = 0; x < N; x++) bits[y].push(rng() > 0.55 ? 1 : 0);
  }
  // finder patterns
  const place = (ox, oy) => {
    for (let y = 0; y < 7; y++) {
      for (let x = 0; x < 7; x++) {
        const onBorder = y === 0 || y === 6 || x === 0 || x === 6;
        const innerBox = y >= 2 && y <= 4 && x >= 2 && x <= 4;
        bits[oy + y][ox + x] = onBorder || innerBox ? 1 : 0;
      }
    }
  };
  place(0, 0);
  place(0, N - 7);
  place(N - 7, 0);
  // timing rows (cosmetic)
  for (let i = 8; i < N - 8; i++) {
    bits[6][i] = i % 2;
    bits[i][6] = i % 2;
  }
  let rects = "";
  for (let y = 0; y < N; y++) {
    for (let x = 0; x < N; x++) {
      if (bits[y][x]) rects += `<rect x="${x * cell}" y="${y * cell}" width="${cell}" height="${cell}" fill="#3d2b1f"/>`;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="160" height="160"><rect width="${size}" height="${size}" fill="#fff"/>${rects}</svg>`;
}

function hashSeed(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
function mulberry32(a) {
  return function () {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function escapeHtml(s) {
  return (s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
