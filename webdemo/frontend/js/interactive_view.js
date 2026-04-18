import { state, clearInteractive, insertDynamicNarrative } from "./state.js";
import { postInteract, postPlacements, postCreatePropsSmart } from "./api.js";
import { listenOnce, asrSupported } from "./asr.js";
import { playTTS, stopTTS } from "./tts.js";
import { toast, showLoader, hideLoader, startHintRotation, stopHintRotation } from "./toast.js";
import { goToNode } from "./router.js";
import { renderTimeline } from "./timeline.js";

let scene = null;

export function mountInteractive(sceneData) {
  scene = sceneData;
  clearInteractive();

  const stage = document.getElementById("stage");
  stage.innerHTML = `
    <div class="goal-banner">
      <span class="goal-icon">🎯</span>
      <span class="goal-text">${escapeHtml(scene.interaction_goal || "")}</span>
      <span class="hint">把物品拖到画面上，选 0/1/2 个再告诉我要做什么</span>
    </div>
    <div class="int-body">
      <div class="tray" id="tray"></div>
      <div class="bg-stage" id="bg-stage">
        <img class="bg-img" src="${scene.background_url}" alt="背景" draggable="false" />
      </div>
    </div>
    <div class="action-bar sticky">
      <div class="selection-chips" id="selection-chips"></div>
      <input type="text" id="action-input" placeholder="告诉我这一刻发生了什么..." />
      <button class="mic" id="action-mic" ${asrSupported() ? "" : "disabled"}>🎤</button>
      <button class="chip prop-toggle" id="btn-make-prop" title="把输入变成新物品">✨</button>
      <button id="action-confirm">加入序列</button>
    </div>
  `;

  const side = document.getElementById("side");
  side.innerHTML = `
    <h2>第 ${scene.index} 幕 · 互动</h2>
    <div class="summary">可以连续安排多个动作，最后一次性变出新的故事段落 ✨</div>
    <div class="op-list" id="op-list"></div>
    <div class="finish-wrap">
      <button class="finish-btn" id="finish-btn" disabled>完成并生成新段落 🎨</button>
    </div>
  `;

  wireStageClicks();
  wireActionBar();
  wireBgDropZone();
  document.getElementById("finish-btn").onclick = onFinish;

  state.interactive.tray = scene.props.map((p) => ({
    name: p.name, kind: "object", url: p.url, custom_url: null,
  }));
  state.interactive.items = [];
  renderTray();

  loadAndPlaceCharacters();

  if (scene.interaction_goal) {
    setTimeout(() => playTTS(scene.interaction_goal, { tone: "温柔" }), 300);
  }
}

export function unmountInteractive() {
  stopTTS();
  stopHintRotation();
  hideLoader();
  scene = null;
}

// ---- character placement via Qwen ----

async function loadAndPlaceCharacters() {
  let llm = null;
  try {
    const resp = await postPlacements(scene.index);
    llm = Object.fromEntries(resp.placements.map((p) => [p.name, p]));
  } catch (e) {
    console.warn("placement failed, fallback:", e.message);
  }
  const fallback = {};
  scene.characters.forEach((c, i) => {
    fallback[c.name] = {
      x: c.default_x ?? (0.2 + 0.6 * i / Math.max(1, scene.characters.length - 1)),
      y: 0.72, scale: 1.0, rotation: 0,
    };
  });
  scene.characters.forEach((c) => {
    const pos = (llm && llm[c.name]) || fallback[c.name];
    const item = {
      name: c.name, kind: "character", url: c.url,
      x: clamp01(pos.x), y: clamp01(pos.y),
      scale: clampScale(pos.scale ?? 1.0),
      rotation: pos.rotation ?? 0,
      custom_url: null,
    };
    state.interactive.items.push(item);
    renderItem(item);
  });
  state.interactive.placementLoaded = true;
  refreshSelectionUI();
}

// ---- tray ----

function renderTray() {
  const tray = document.getElementById("tray");
  if (!tray) return;
  tray.innerHTML = "";

  // pending placeholders first
  state.interactive.pendingProps
    .filter((p) => !p.resolved)
    .forEach((p) => {
      const el = document.createElement("div");
      el.className = "tray-pending";
      el.innerHTML = `<div class="mini-spinner"></div><div class="label">${escapeHtml(p.label)}</div>`;
      tray.appendChild(el);
    });

  if (state.interactive.tray.length === 0 && state.interactive.pendingProps.length === 0) {
    tray.innerHTML = '<div class="tray-empty">托盘空啦，用下面 ✨ 或说出想要的东西</div>';
    return;
  }

  state.interactive.tray.forEach((it) => {
    const cell = document.createElement("div");
    cell.className = `tray-item ${it.kind}`;
    cell.draggable = true;
    cell.dataset.name = it.name;
    cell.dataset.kind = it.kind;
    cell.innerHTML = `<img src="${it.custom_url || it.url}" alt="${escapeHtml(it.name)}" /><div class="name">${escapeHtml(it.name)}</div>`;
    cell.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("application/json", JSON.stringify({ name: it.name }));
      e.dataTransfer.effectAllowed = "move";
      cell.classList.add("dragging");
    });
    cell.addEventListener("dragend", () => cell.classList.remove("dragging"));
    tray.appendChild(cell);
  });
}

function wireBgDropZone() {
  const bg = document.getElementById("bg-stage");
  bg.addEventListener("dragover", (e) => {
    if (e.dataTransfer.types.includes("application/json")) {
      e.preventDefault();
      bg.classList.add("drag-over");
    }
  });
  bg.addEventListener("dragleave", () => bg.classList.remove("drag-over"));
  bg.addEventListener("drop", (e) => {
    e.preventDefault();
    bg.classList.remove("drag-over");
    let payload;
    try { payload = JSON.parse(e.dataTransfer.getData("application/json")); } catch { return; }
    const idx = state.interactive.tray.findIndex((t) => t.name === payload.name);
    if (idx < 0) return;
    const [tItem] = state.interactive.tray.splice(idx, 1);
    const rect = bg.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const item = {
      name: tItem.name, kind: tItem.kind,
      url: tItem.url, custom_url: tItem.custom_url,
      x: clamp01(x), y: clamp01(y), scale: 1.0, rotation: 0,
    };
    state.interactive.items.push(item);
    renderItem(item);
    renderTray();
    refreshSelectionUI();
  });
}

// ---- render stage item ----

function renderItem(item) {
  const bg = document.getElementById("bg-stage");
  const img = document.createElement("img");
  img.src = item.custom_url || item.url;
  img.alt = item.name;
  img.draggable = false;
  img.className = "stage-item";
  img.dataset.name = item.name;
  img.dataset.kind = item.kind;
  applyTransform(img, item);
  img.addEventListener("pointerdown", onItemPointerDown);
  img.addEventListener("click", onItemClick);
  bg.appendChild(img);
}

function applyTransform(el, it) {
  el.style.left = `${it.x * 100}%`;
  el.style.top = `${it.y * 100}%`;
  el.style.setProperty("--s", it.scale);
  el.style.setProperty("--r", `${it.rotation}deg`);
}

function getItem(name) {
  return state.interactive.items.find((i) => i.name === name);
}

function updateItem(name, patch) {
  const it = getItem(name);
  if (!it) return;
  Object.assign(it, patch);
  const el = document.querySelector(`.stage-item[data-name="${CSS.escape(name)}"]`);
  if (el) applyTransform(el, it);
}

// ---- selection + drag/rotate/scale ----

function wireStageClicks() {
  const bg = document.getElementById("bg-stage");
  bg.addEventListener("click", (e) => {
    if (e.target.closest(".stage-item") || e.target.closest(".item-handle") || e.target.closest(".action-bar")) return;
    state.interactive.selection = [];
    refreshSelectionUI();
  });
}

function onItemClick(e) {
  if (drag.active) return;
  e.stopPropagation();
  const name = e.currentTarget.dataset.name;
  const sel = state.interactive.selection;
  const idx = sel.indexOf(name);
  if (idx >= 0) sel.splice(idx, 1);
  else {
    if (sel.length >= 2) sel.shift();
    sel.push(name);
  }
  refreshSelectionUI();
}

const drag = { active: false, mode: null, name: null, startX: 0, startY: 0, origin: null };

function onItemPointerDown(e) {
  const el = e.currentTarget;
  const name = el.dataset.name;
  if (e.target.classList?.contains?.("item-handle")) return;
  drag.active = false;
  drag.mode = "move";
  drag.name = name;
  drag.startX = e.clientX;
  drag.startY = e.clientY;
  drag.origin = { ...getItem(name) };
  window.addEventListener("pointermove", onDragMove);
  window.addEventListener("pointerup", onDragUp, { once: true });
}

function onDragMove(e) {
  const dx = e.clientX - drag.startX;
  const dy = e.clientY - drag.startY;
  if (!drag.active && Math.hypot(dx, dy) > 6) drag.active = true;
  if (!drag.active) return;
  const bg = document.getElementById("bg-stage");
  const rect = bg.getBoundingClientRect();
  if (drag.mode === "move") {
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    updateItem(drag.name, { x: clamp01(x), y: clamp01(y) });
    refreshSelectionUI();
  } else if (drag.mode === "scale") {
    const it = getItem(drag.name);
    const cx = rect.left + it.x * rect.width;
    const cy = rect.top + it.y * rect.height;
    const origDist = Math.hypot(drag.startX - cx, drag.startY - cy) || 1;
    const curDist = Math.hypot(e.clientX - cx, e.clientY - cy);
    updateItem(drag.name, { scale: clampScale(drag.origin.scale * (curDist / origDist)) });
    refreshSelectionUI();
  } else if (drag.mode === "rotate") {
    const it = getItem(drag.name);
    const cx = rect.left + it.x * rect.width;
    const cy = rect.top + it.y * rect.height;
    const origAngle = Math.atan2(drag.startY - cy, drag.startX - cx);
    const curAngle = Math.atan2(e.clientY - cy, e.clientX - cx);
    const deltaDeg = ((curAngle - origAngle) * 180) / Math.PI;
    const rotation = ((drag.origin.rotation + deltaDeg + 540) % 360) - 180;
    updateItem(drag.name, { rotation });
    refreshSelectionUI();
  }
}

function onDragUp() {
  window.removeEventListener("pointermove", onDragMove);
  setTimeout(() => { drag.active = false; drag.mode = null; drag.name = null; }, 0);
}

// ---- handles ----

function refreshSelectionUI() {
  const bg = document.getElementById("bg-stage");
  if (!bg) return;
  [...bg.querySelectorAll(".item-handles")].forEach((n) => n.remove());
  const chips = document.getElementById("selection-chips");
  chips.innerHTML = "";
  const sel = state.interactive.selection;
  sel.forEach((name, i) => {
    const chip = document.createElement("span");
    chip.className = `sel-chip role-${i}`;
    chip.textContent = name;
    chip.onclick = () => {
      state.interactive.selection = sel.filter((n) => n !== name);
      refreshSelectionUI();
    };
    chips.appendChild(chip);
  });
  const input = document.getElementById("action-input");
  if (input) {
    if (sel.length === 0) input.placeholder = "告诉我这一刻发生了什么...";
    else if (sel.length === 1) input.placeholder = `让「${sel[0]}」做什么？`;
    else input.placeholder = `让「${sel[0]}」对「${sel[1]}」做什么？`;
  }
  sel.forEach((name, i) => attachHandles(name, i));
}

function attachHandles(name, roleIdx) {
  const bg = document.getElementById("bg-stage");
  const item = getItem(name);
  if (!item) return;
  const el = bg.querySelector(`.stage-item[data-name="${CSS.escape(name)}"]`);
  if (!el) return;

  const group = document.createElement("div");
  group.className = `item-handles role-${roleIdx}`;
  const rect = el.getBoundingClientRect();
  const bgRect = bg.getBoundingClientRect();
  const cx = ((rect.left + rect.right) / 2 - bgRect.left) / bgRect.width;
  const cy = ((rect.top + rect.bottom) / 2 - bgRect.top) / bgRect.height;
  const halfW = (rect.width / 2) / bgRect.width;
  const halfH = (rect.height / 2) / bgRect.height;

  group.style.left = `${cx * 100}%`;
  group.style.top = `${cy * 100}%`;
  group.style.width = `${halfW * 2 * 100}%`;
  group.style.height = `${halfH * 2 * 100}%`;

  const hDel = makeHandle("↩︎", "del", "top-left");
  hDel.title = "返回托盘";
  hDel.onclick = (e) => { e.stopPropagation(); returnToTray(name); };
  const hRot = makeHandle("↻", "rot", "top-right");
  hRot.addEventListener("pointerdown", (e) => startHandleDrag(e, name, "rotate"));
  const hScl = makeHandle("⤡", "scl", "bottom-right");
  hScl.addEventListener("pointerdown", (e) => startHandleDrag(e, name, "scale"));
  group.appendChild(hDel);
  group.appendChild(hRot);
  group.appendChild(hScl);
  bg.appendChild(group);
}

function makeHandle(icon, cls, pos) {
  const b = document.createElement("button");
  b.className = `item-handle ${cls} ${pos}`;
  b.innerHTML = icon;
  return b;
}

function startHandleDrag(e, name, mode) {
  e.stopPropagation();
  drag.active = true;
  drag.mode = mode;
  drag.name = name;
  drag.startX = e.clientX;
  drag.startY = e.clientY;
  drag.origin = { ...getItem(name) };
  window.addEventListener("pointermove", onDragMove);
  window.addEventListener("pointerup", onDragUp, { once: true });
}

function returnToTray(name) {
  const idx = state.interactive.items.findIndex((i) => i.name === name);
  if (idx < 0) return;
  const [item] = state.interactive.items.splice(idx, 1);
  state.interactive.tray.push({
    name: item.name, kind: item.kind, url: item.url, custom_url: item.custom_url,
  });
  state.interactive.selection = state.interactive.selection.filter((n) => n !== name);
  document.querySelector(`.stage-item[data-name="${CSS.escape(name)}"]`)?.remove();
  renderTray();
  refreshSelectionUI();
}

// ---- action bar ----

function wireActionBar() {
  document.getElementById("action-confirm").onclick = confirmAction;
  document.getElementById("action-mic").onclick = doMic;
  document.getElementById("btn-make-prop").onclick = smartCreateFromInput;
  document.getElementById("action-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") confirmAction();
  });
}

function confirmAction() {
  const actionEl = document.getElementById("action-input");
  const action = (actionEl.value || "").trim();
  if (!action) { toast("请先说一下要做什么～"); return; }
  const sel = state.interactive.selection;
  const op = { subject: null, subject_kind: null, target: null, target_kind: null, action };
  if (sel[0]) {
    const it = getItem(sel[0]);
    if (it) { op.subject = it.name; op.subject_kind = it.kind; }
  }
  if (sel[1]) {
    const it = getItem(sel[1]);
    if (it) { op.target = it.name; op.target_kind = it.kind; }
  }
  state.interactive.ops.push(op);
  state.interactive.selection = [];
  actionEl.value = "";
  refreshSelectionUI();
  renderOps();
}

function smartCreateFromInput() {
  const input = document.getElementById("action-input");
  const text = (input.value || "").trim();
  if (!text) { toast("先输入或说出想要的东西～"); return; }
  input.value = "";
  startBackgroundCreate(text);
}

function startBackgroundCreate(text) {
  const id = `pend-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 6)}`;
  const existingNames = [
    ...state.interactive.tray.map((t) => t.name),
    ...state.interactive.items.map((i) => i.name),
    ...state.interactive.customProps.map((c) => c.name),
  ];
  const entry = { id, label: `✨ ${text}`, promise: null, resolved: false, ok: false };
  state.interactive.pendingProps.push(entry);
  renderTray();
  toast("开始在后台画新物品，可以继续操作～");

  entry.promise = (async () => {
    try {
      const resp = await postCreatePropsSmart({
        session_id: state.sessionId,
        scene_idx: scene.index,
        text,
        _existing: existingNames, // reserved for future use
      });
      resp.props.forEach((p) => {
        // de-dup against current tray/items
        const taken = new Set([
          ...state.interactive.tray.map((t) => t.name),
          ...state.interactive.items.map((i) => i.name),
        ]);
        let finalName = p.name;
        let k = 2;
        while (taken.has(finalName)) {
          finalName = `${p.name}${k}`;
          k += 1;
        }
        state.interactive.tray.push({
          name: finalName, kind: "object", url: p.url, custom_url: p.url,
        });
        state.interactive.customProps.push({ name: finalName, url: p.url });
      });
      entry.resolved = true;
      entry.ok = true;
      toast(`变出来了：${resp.props.map((p) => p.name).join("、")}`);
    } catch (e) {
      entry.resolved = true;
      entry.ok = false;
      toast(`生成失败：${e.message}`);
    } finally {
      renderTray();
    }
  })();
}

async function doMic() {
  const btn = document.getElementById("action-mic");
  if (!asrSupported()) { toast("浏览器不支持语音，请直接输入"); return; }
  btn.classList.add("listening");
  try {
    const text = await listenOnce({ lang: "zh-CN" });
    btn.classList.remove("listening");
    document.getElementById("action-input").value = text;
  } catch (e) {
    btn.classList.remove("listening");
    toast(`没听清：${e.message}`);
  }
}

// ---- op list ----

function renderOps() {
  const list = document.getElementById("op-list");
  list.innerHTML = "";
  state.interactive.ops.forEach((op, i) => {
    const chip = document.createElement("div");
    chip.className = "op-chip";
    chip.draggable = true;
    chip.dataset.idx = String(i);
    let txt;
    if (op.subject && op.target) txt = `让「${op.subject}」对「${op.target}」：${op.action}`;
    else if (op.subject) txt = `让「${op.subject}」：${op.action}`;
    else txt = `场景事件：${op.action}`;
    chip.innerHTML = `
      <button class="del" title="删除">✕</button>
      <strong>${i + 1}. </strong>${escapeHtml(txt).replace(/「(.+?)」/g, "「<b>$1</b>」")}
    `;
    chip.querySelector(".del").onclick = (e) => {
      e.stopPropagation();
      state.interactive.ops.splice(i, 1);
      renderOps();
    };
    chip.addEventListener("dragstart", onOpDragStart);
    chip.addEventListener("dragover", onOpDragOver);
    chip.addEventListener("dragleave", onOpDragLeave);
    chip.addEventListener("drop", onOpDrop);
    chip.addEventListener("dragend", onOpDragEnd);
    list.appendChild(chip);
  });
  document.getElementById("finish-btn").disabled = state.interactive.ops.length === 0;
}

function onOpDragStart(e) {
  const idx = e.currentTarget.dataset.idx;
  e.dataTransfer.setData("application/x-op-idx", idx);
  e.dataTransfer.effectAllowed = "move";
  e.currentTarget.classList.add("dragging");
}

function onOpDragOver(e) {
  if (!e.dataTransfer.types.includes("application/x-op-idx")) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
  const rect = e.currentTarget.getBoundingClientRect();
  const above = e.clientY < rect.top + rect.height / 2;
  document.querySelectorAll(".op-chip").forEach((n) => {
    if (n !== e.currentTarget) n.classList.remove("drop-above", "drop-below");
  });
  e.currentTarget.classList.toggle("drop-above", above);
  e.currentTarget.classList.toggle("drop-below", !above);
}

function onOpDragLeave(e) {
  e.currentTarget.classList.remove("drop-above", "drop-below");
}

function onOpDrop(e) {
  e.preventDefault();
  const fromIdx = parseInt(e.dataTransfer.getData("application/x-op-idx"), 10);
  const toIdx = parseInt(e.currentTarget.dataset.idx, 10);
  const rect = e.currentTarget.getBoundingClientRect();
  const above = e.clientY < rect.top + rect.height / 2;
  moveOp(fromIdx, toIdx, above);
  document.querySelectorAll(".op-chip").forEach((n) => n.classList.remove("drop-above", "drop-below", "dragging"));
}

function onOpDragEnd(e) {
  e.currentTarget.classList.remove("dragging");
  document.querySelectorAll(".op-chip").forEach((n) => n.classList.remove("drop-above", "drop-below"));
}

function moveOp(from, to, above) {
  if (Number.isNaN(from) || Number.isNaN(to)) return;
  if (from === to) return;
  const ops = state.interactive.ops;
  const [item] = ops.splice(from, 1);
  let dest = above ? to : to + 1;
  if (from < dest) dest -= 1;
  ops.splice(dest, 0, item);
  renderOps();
}

// ---- finish (with pending-prop confirmation) ----

function confirmModal({ title, body, confirm = "确定", cancel = "取消" }) {
  return new Promise((resolve) => {
    const existing = document.getElementById("generic-confirm");
    if (existing) existing.remove();
    const m = document.createElement("div");
    m.id = "generic-confirm";
    m.className = "modal";
    m.innerHTML = `
      <div class="modal-box">
        <h3>${escapeHtml(title)}</h3>
        <div class="modal-hint">${escapeHtml(body)}</div>
        <div class="modal-actions">
          <button class="secondary" id="gc-cancel">${escapeHtml(cancel)}</button>
          <button id="gc-ok">${escapeHtml(confirm)}</button>
        </div>
      </div>
    `;
    document.body.appendChild(m);
    document.getElementById("gc-cancel").onclick = () => { m.remove(); resolve(false); };
    document.getElementById("gc-ok").onclick = () => { m.remove(); resolve(true); };
  });
}

async function onFinish() {
  const ops = state.interactive.ops;
  if (!ops.length) return;
  const pending = state.interactive.pendingProps.filter((p) => !p.resolved);
  if (pending.length > 0) {
    const go = await confirmModal({
      title: "还有新物品在后台生成",
      body: `有 ${pending.length} 个新物品还没画完。要直接进入下一幕吗？（没画完的会跳过）`,
      confirm: "直接生成下一幕",
      cancel: "等它们好",
    });
    if (!go) {
      showLoader("等新物品画完…");
      startHintRotation();
      try {
        await Promise.allSettled(pending.map((p) => p.promise));
      } finally {
        stopHintRotation();
        hideLoader();
      }
    }
  }

  const placements = state.interactive.items.map((it) => ({
    name: it.name, kind: it.kind,
    x: it.x, y: it.y, scale: it.scale, rotation: it.rotation,
    custom_url: it.custom_url || null,
  }));
  state.interactive.status = "generating";
  showLoader("AI 正在把你的故事变成画…");
  startHintRotation();
  try {
    const resp = await postInteract({
      session_id: state.sessionId,
      scene_idx: scene.index,
      placements,
      ops,
      custom_props: state.interactive.customProps,
    });
    state.interactive.status = "done";
    // record interaction snapshot for the final report
    state.storyLog.interactions.push({
      scene_idx: scene.index,
      interaction_goal: scene.interaction_goal || "",
      ops: ops.map((o) => ({ ...o })),
      custom_props: state.interactive.customProps.map((c) => ({ ...c })),
      dynamic_summary: resp.summary || "",
    });
    const newIdx = insertDynamicNarrative(state.cursor, resp);
    state.highestUnlocked = Math.max(state.highestUnlocked, newIdx);
    renderTimeline();
    await goToNode(newIdx);
  } catch (e) {
    toast(`生成失败：${e.message}`);
    state.interactive.status = "idle";
  } finally {
    stopHintRotation();
    hideLoader();
  }
}

// ---- helpers ----

function clamp01(v) { return Math.max(0.02, Math.min(0.98, Number(v) || 0.5)); }
function clampScale(v) { return Math.max(0.3, Math.min(3.0, Number(v) || 1.0)); }

function escapeHtml(s) {
  return (s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
