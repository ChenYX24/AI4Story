import { postReport } from "./api.js";
import { state } from "./state.js";
import { showLoader, hideLoader, startHintRotation, stopHintRotation, toast } from "./toast.js";
import { stopTTS } from "./tts.js";

export async function showReport() {
  stopTTS();
  state.stage = "report";
  const stage = document.getElementById("stage");
  const side = document.getElementById("side");
  stage.innerHTML = `<div class="report-loading">正在为你和爸爸妈妈写报告...</div>`;
  side.innerHTML = "";

  showLoader("AI 正在整理这场旅程…");
  startHintRotation();
  try {
    const resp = await postReport({
      session_id: state.sessionId,
      story_id: state.storyId || "little_red_riding_hood",
      interactions: state.storyLog.interactions,
    });
    renderReport(resp);
  } catch (e) {
    stage.innerHTML = `<div class="report-loading error">报告生成失败：${e.message}</div>`;
    toast("报告生成失败，稍后再试～");
  } finally {
    stopHintRotation();
    hideLoader();
  }
}

function renderReport(data) {
  const stage = document.getElementById("stage");
  const kid = data.kid_section || {};
  const parent = data.parent_section || {};
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
            <h3>🧩 观察到的性格/行为倾向</h3>
            <ul>${(parent.traits || []).map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>
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
  document.getElementById("report-back").onclick = () => {
    state.stage = "playing";
    // go back to last flow node
    import("./router.js").then((m) => m.goToNode(state.cursor));
  };
  document.getElementById("report-restart").onclick = () => {
    window.location.reload();
  };
}

function escapeHtml(s) {
  return (s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
