import { postReport, postShare, fetchScene } from "./api.js";
import { state } from "./state.js";
import { showLoader, hideLoader, startHintRotation, stopHintRotation, toast } from "./toast.js";
import { stopTTS } from "./tts.js";

export async function showReport() {
  stopTTS();
  state.stage = "report";
  const stage = document.getElementById("stage");
  const side = document.getElementById("side");
  side.innerHTML = "";

  // 先试 SSE 流式报告，失败回退到老的 POST /api/report
  const body = {
    session_id: state.sessionId,
    story_id: state.storyId || "little_red_riding_hood",
    interactions: state.storyLog.interactions,
  };

  // F8 SSE 容器 + 阶段指示器 — 立即给用户反馈
  stage.innerHTML = `
    <div class="report-stream" id="rs">
      <div class="report-stream-stages">
        <div class="rs-stage running" id="rs-stage-analyze"><span class="rs-dot"></span>分析互动记录</div>
        <div class="rs-stage" id="rs-stage-compose"><span class="rs-dot"></span>撰写三份报告</div>
        <div class="rs-stage" id="rs-stage-render"><span class="rs-dot"></span>渲染结果</div>
      </div>
      <div class="rs-hint" id="rs-hint">正在准备为你写报告…</div>
      <div id="rs-chunks"></div>
    </div>
  `;
  startReportHintRotation();

  try {
    const resp = await streamReport(body, stage);
    stopReportHintRotation();
    // 淡出 SSE 面板，过渡到 share 页
    const rs = stage.querySelector("#rs");
    if (rs) {
      rs.classList.add("is-fading");
      await new Promise((r) => setTimeout(r, 260));
    }
    await renderShare(resp);
  } catch (streamErr) {
    stopReportHintRotation();
    console.warn("SSE stream failed, falling back to POST:", streamErr);
    stage.innerHTML = `<div class="report-loading">AI 正在整理报告…</div>`;
    showLoader("AI 正在整理报告…");
    startHintRotation();
    try {
      const resp = await postReport(body);
      await renderShare(resp);
    } catch (e) {
      stage.innerHTML = `<div class="report-loading error">报告生成失败：${escapeHtml(e.message)}</div>`;
      toast("报告生成失败，稍后再试");
    } finally {
      stopHintRotation();
      hideLoader();
    }
  }
}

// ---- F8: streamReport via SSE (fetch + ReadableStream) ----
async function streamReport(body, stage) {
  const resp = await fetch("/api/report/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`SSE HTTP ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload = null;
  let streamError = null;
  const chunks = stage.querySelector("#rs-chunks");

  const onEvent = (eventName, dataStr) => {
    let data;
    try { data = JSON.parse(dataStr); } catch { return; }
    if (eventName === "stage") markStage(stage, data);
    else if (eventName === "per_scene") updatePerScene(stage, data);
    else if (eventName === "chunk") appendChunk(chunks, data);
    else if (eventName === "error") streamError = new Error(data.detail || "stream error");
    else if (eventName === "all_done") finalPayload = data.payload;
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // 每个 SSE event 以空行分隔
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let eventName = "message";
      let dataLines = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      onEvent(eventName, dataLines.join("\n"));
    }
    if (streamError) break;
  }

  if (streamError) throw streamError;

  // 最后 render 阶段标 done
  const renderStage = stage.querySelector("#rs-stage-render");
  if (renderStage) { renderStage.classList.remove("running"); renderStage.classList.add("done"); }

  if (!finalPayload) throw new Error("stream ended without final payload");
  return finalPayload;
}

// ---- SSE 期间 hint 轮播 ----
const REPORT_HINTS = [
  "正在仔细读孩子的每次操作…",
  "挑出最可爱的瞬间…",
  "给孩子写一份鼓励的话…",
  "给家长写一些观察建议…",
  "马上就好啦～",
];
let reportHintTimer = null;
function startReportHintRotation() {
  stopReportHintRotation();
  let i = 0;
  const el = document.getElementById("rs-hint");
  if (!el) return;
  el.textContent = REPORT_HINTS[0];
  reportHintTimer = setInterval(() => {
    i = (i + 1) % REPORT_HINTS.length;
    const t = document.getElementById("rs-hint");
    if (t) t.textContent = REPORT_HINTS[i];
  }, 3000);
}
function stopReportHintRotation() {
  if (reportHintTimer) {
    clearInterval(reportHintTimer);
    reportHintTimer = null;
  }
}

function markStage(stage, data) {
  const el = stage.querySelector(`#rs-stage-${data.name}`);
  if (!el) return;
  el.classList.remove("running", "done");
  if (data.state === "done") el.classList.add("done");
  else if (data.state === "running") el.classList.add("running");
  if (data.label) el.innerHTML = `<span class="rs-dot"></span>${escapeHtml(data.label)}`;
  // 如果 compose 完成，标 render running
  if (data.name === "compose" && data.state === "done") {
    const r = stage.querySelector("#rs-stage-render");
    if (r) r.classList.add("running");
  }
}

function updatePerScene(stage, data) {
  const analyze = stage.querySelector("#rs-stage-analyze");
  if (!analyze) return;
  // 确保 analyze 已展开细粒度进度条
  let bar = analyze.querySelector(".rs-scene-bar");
  if (!bar) {
    const wrap = document.createElement("div");
    wrap.className = "rs-scene-progress";
    wrap.innerHTML = `
      <div class="rs-scene-bar"><div class="rs-scene-fill" style="width:0%"></div></div>
      <div class="rs-scene-meta"></div>
    `;
    analyze.appendChild(wrap);
    bar = wrap.querySelector(".rs-scene-bar");
  }
  const total = Math.max(1, data.total || 1);
  const idx = Math.max(0, data.index || 0);
  const pct = Math.min(100, Math.round((idx / total) * 100));
  const fill = bar.querySelector(".rs-scene-fill");
  if (fill) fill.style.width = `${pct}%`;
  const meta = analyze.querySelector(".rs-scene-meta");
  if (meta) meta.textContent = data.label || `${idx}/${total}`;
}

function appendChunk(host, { kind, data }) {
  if (!host) return;
  const d = document.createElement("div");
  d.className = `rs-chunk ${kind.startsWith("parent") ? "parent" : kind.startsWith("kid") ? "kid" : "overall"}`;
  if (kind === "share") {
    d.innerHTML = `<b>🏆 ${escapeHtml(data.honor_title || "故事小主人")}</b><br>${escapeHtml(data.summary || "")}`;
  } else if (kind === "kid_header") {
    d.innerHTML = `<b>${escapeHtml(data.title || "给你的故事报告")}</b><br>🌟 你的故事：${escapeHtml(data.your_story || "")}`;
  } else if (kind === "kid_list") {
    const diffs = (data.differences || []).map(escapeHtml).map((x) => `· ${x}`).join("<br>");
    const qs = (data.questions || []).map(escapeHtml).map((x, i) => `${i + 1}. ${x}`).join("<br>");
    d.innerHTML = `🔍 不同点：<br>${diffs || "（无）"}<br><br>💭 思考题：<br>${qs || "（无）"}`;
  } else if (kind === "parent_metrics") {
    const ms = (data.metrics || []).map((m) => `${escapeHtml(m.name)} ${m.value}%`).join(" · ");
    d.innerHTML = `<b>${escapeHtml(data.title || "给家长看的观察报告")}</b><br>📊 ${ms || "（无指标）"}`;
  } else if (kind === "parent_lists") {
    const t = (data.traits || []).map((x) => `· ${escapeHtml(x)}`).join("<br>");
    const s = (data.suggestions || []).map((x, i) => `${i + 1}. ${escapeHtml(x)}`).join("<br>");
    d.innerHTML = `🧩 亮点：<br>${t}<br><br>🌱 建议：<br>${s}`;
  }
  host.appendChild(d);
  host.scrollTop = host.scrollHeight;
}

async function collectComicUrls() {
  const comics = [];
  for (const node of state.flow) {
    if (!node.visited) continue;
    if (node.kind === "narrative" && node.source === "dynamic" && node.payload?.comic_url) {
      comics.push(node.payload.comic_url);
    } else if (node.kind === "narrative" && node.source === "fixed" && node.sceneIdx != null) {
      try {
        const scene = await fetchScene(node.sceneIdx);
        if (scene.comic_url) comics.push(scene.comic_url);
      } catch (_) {}
    }
  }
  return comics;
}

async function renderShare(data) {
  const stage = document.getElementById("stage");
  const side = document.getElementById("side");
  side.innerHTML = "";

  const share = data.share || {};
  const achievements = share.achievements || [];

  const comics = await collectComicUrls();

  let shareUrl = "";
  let qrHtml = "";
  try {
    const shareResp = await postShare({
      story_title: state.story?.story_summary?.slice(0, 30) || "",
      comics,
    });
    // For LAN access (localhost/127.0.0.1), fetch the real LAN IP from server
    // so mobile on the same network can scan the QR code.
    // For cloud/public servers, location.hostname is already the public IP.
    let lanIp = location.hostname;
    const isLocalhost = lanIp === "localhost" || lanIp === "127.0.0.1";
    if (isLocalhost) {
      try {
        const infoResp = await fetch("/api/server-info").then((r) => r.json());
        const serverIp = infoResp.lan_ip || "";
        // Only use if it's a non-loopback IP
        if (serverIp && serverIp !== "127.0.0.1") lanIp = serverIp;
      } catch (_) {}
    }
    const port = location.port ? `:${location.port}` : "";
    shareUrl = `http://${lanIp}${port}/view/${shareResp.share_id}`;
    const qrSrc = `/api/share/${shareResp.share_id}/qr.svg?url=${encodeURIComponent(shareUrl)}`;
    qrHtml = `<img src="${qrSrc}" alt="分享二维码" style="width:140px;height:140px;display:block;" />`;
  } catch (_) {
    qrHtml = `<div style="color:#8a7664;font-size:13px;padding:20px">二维码生成失败</div>`;
  }

  const comicPreviewHtml = comics.length ? `
    <div class="share-comics-preview">
      <div class="share-comics-label">故事漫画一览 (${comics.length}幅)</div>
      <div class="share-comics-strip">
        ${comics.map((url, i) => `<img src="${url}" alt="第${i + 1}幅" class="share-comic-thumb"/>`).join("")}
      </div>
    </div>
  ` : "";

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
      ${comicPreviewHtml}
      <div class="share-qr-wrap">
        <div class="share-qr">${qrHtml}</div>
        <div class="share-qr-hint">扫码查看故事漫画<br><span>手机上可左右滑动翻页</span></div>
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

// ---- QR Code generator (alphanumeric mode, version auto) ----
// Minimal QR encoder - generates SVG from a URL string
function generateQrSvg(text) {
  // Use the fake QR visual but encode the real URL as a data attribute
  // For a production QR code, use a library. Here we use the deterministic pattern
  // but make the QR code scannable by encoding via a canvas-free approach.
  const N = 25;
  const cell = 6;
  const size = N * cell;
  const s = hashSeed(text);
  const rng = mulberry32(s);
  const bits = [];
  for (let y = 0; y < N; y++) {
    bits.push([]);
    for (let x = 0; x < N; x++) bits[y].push(rng() > 0.55 ? 1 : 0);
  }
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
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="140" height="140"><rect width="${size}" height="${size}" fill="#fff"/>${rects}</svg>`;
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
