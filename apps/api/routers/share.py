import io
import json
import os
import socket
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from ..config import OUTPUTS_ROOT


def _get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _share_base_url(request: Request | None = None) -> str:
    """二维码 / 分享链接里 /view/<id> 的根地址。

    优先级：PUBLIC_BASE_URL（部署侧显式给）→ 同 origin（生产 nginx 把 /view 也代理过来时）
    → 回退到 LAN IP + 实际后端端口（本地开发，Vite 在 127.0.0.1:5173 不可外访，
      所以必须用后端的 0.0.0.0:8000）。
    """
    public_base = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base:
        return public_base
    if request is not None:
        host = request.headers.get("host", "")
        # nginx 转发时 X-Forwarded-Host 才是用户真实访问的 origin
        forwarded_host = request.headers.get("x-forwarded-host", "").strip()
        forwarded_proto = request.headers.get("x-forwarded-proto", "").strip() or "http"
        if forwarded_host:
            return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
        # 直接 host 头不是回环 / Vite 时也认（生产同 origin）
        if host and not host.startswith(("127.0.0.1", "localhost")):
            scheme = request.url.scheme or "http"
            return f"{scheme}://{host}".rstrip("/")
    # 本地开发兜底：LAN IP + 后端端口（默认 8000）
    lan_ip = _get_lan_ip()
    port = os.getenv("PORT", "8000").strip() or "8000"
    return f"http://{lan_ip}:{port}"


router = APIRouter()

SHARES_DIR = OUTPUTS_ROOT / "_shares"
SHARES_DIR.mkdir(parents=True, exist_ok=True)


class ShareCreateRequest(BaseModel):
    story_title: str = ""
    story_id: str = ""
    comics: list[str] = Field(default_factory=list)  # 旧版兜底（仅 url 列表）
    pages: list[dict] = Field(default_factory=list)  # 新版：每页 {comic_url, summary, storyboard}
    props: list[dict] = Field(default_factory=list)


@router.get("/server-info")
def server_info(request: Request) -> dict:
    return {
        "lan_ip": _get_lan_ip(),
        # share_base 用于前端拼 QR / 复制链接，避开 Vite dev port (5173) 不能外访的坑
        "share_base": _share_base_url(request),
    }


@router.get("/share/{share_id}/qr.svg")
def share_qr(share_id: str, url: str = Query(default="")) -> Response:
    p = SHARES_DIR / f"{share_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="分享不存在")
    target_url = url or f"/view/{share_id}"
    try:
        import segno  # type: ignore
        qr = segno.make(target_url, error="L")
        buf = io.BytesIO()
        qr.save(buf, kind="svg", scale=4, border=1)
        return Response(content=buf.getvalue(), media_type="image/svg+xml")
    except ImportError:
        raise HTTPException(status_code=503, detail="segno 未安装，请运行 pip install segno")


@router.post("/share")
def create_share(req: ShareCreateRequest, request: Request) -> dict:
    share_id = uuid.uuid4().hex[:12]
    # pages 优先；如果调用方还在用旧 comics，自动包装一遍，让前端展示逻辑只走一条路。
    pages = list(req.pages or [])
    if not pages and req.comics:
        pages = [{"comic_url": u, "summary": "", "storyboard": []} for u in req.comics]
    data = {
        "id": share_id,
        "story_title": req.story_title,
        "story_id": req.story_id,
        "comics": [p.get("comic_url", "") for p in pages if p.get("comic_url")],
        "pages": pages,
        "props": req.props,
    }
    (SHARES_DIR / f"{share_id}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    base = _share_base_url(request)
    return {"share_id": share_id, "share_url": f"{base}/view/{share_id}"}


@router.get("/share/{share_id}")
def get_share_data(share_id: str) -> dict:
    p = SHARES_DIR / f"{share_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="分享不存在或已过期。")
    return json.loads(p.read_text(encoding="utf-8"))


MOBILE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"/>
<title>漫秀Mind Show</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;font-family:"PingFang SC","Microsoft YaHei",sans-serif;
  background:linear-gradient(135deg,#fdf6ec,#ffe7d5);color:#3d2b1f;-webkit-tap-highlight-color:transparent}
body{display:flex;flex-direction:column;min-height:100%}
.header{text-align:center;padding:14px 12px 6px;flex-shrink:0}
.header h1{font-size:20px;font-weight:800;
  background:linear-gradient(135deg,#ff8a5b,#ffd24d);-webkit-background-clip:text;background-clip:text;color:transparent}
.header p{font-size:13px;color:#8a7664;margin-top:4px}
.page{flex:1;display:flex;flex-direction:column;padding:0 14px 10px;min-height:0}
.summary{font-size:14px;line-height:1.55;color:#5b4534;background:#fff;border-radius:14px;
  padding:10px 14px;margin:6px 0 10px;box-shadow:0 4px 14px rgba(61,43,31,.10);flex-shrink:0}
.summary .label{font-size:11px;font-weight:700;color:#a47148;letter-spacing:1px;margin-right:4px}
.deck{position:relative;flex:0 0 auto;display:flex;align-items:center;justify-content:center;
  overflow:hidden;touch-action:pan-y;height:62vw;max-height:540px;width:100%}
.slide{position:absolute;width:92%;max-width:520px;aspect-ratio:1/1;border-radius:18px;
  box-shadow:0 8px 28px rgba(61,43,31,0.18);background:#fff;
  transition:transform .35s ease,opacity .35s ease;will-change:transform,opacity;user-select:none;overflow:hidden}
.slide img{width:100%;height:100%;object-fit:contain;border-radius:18px;pointer-events:none}
.counter{text-align:center;padding:6px 0;font-size:13px;color:#8a7664;font-weight:600;flex-shrink:0}
.bubbles{flex:1;min-height:0;overflow-y:auto;display:flex;flex-direction:column;gap:8px;padding:6px 2px 8px}
.bubble{background:#fff;border-radius:14px;padding:9px 12px;box-shadow:0 3px 10px rgba(61,43,31,.10);
  font-size:14px;line-height:1.55;cursor:pointer;border:2px solid transparent;transition:all .2s;position:relative;
  display:flex;flex-direction:column;gap:2px}
.bubble.narration{background:#fff7e6;border-color:#ffd99a55}
.bubble.dialogue{background:#fff}
.bubble.playing{border-color:#ff8a5b;box-shadow:0 0 14px rgba(255,138,91,.35);background:#fff3e6}
.bubble .speaker{font-size:11px;font-weight:700;color:#a47148}
.bubble .speaker .tone{color:#baa994;font-weight:500;margin-left:6px}
.bubble .text{color:#3d2b1f}
.bubble .play-icon{position:absolute;right:8px;top:8px;font-size:13px;opacity:.55}
.bubble.playing .play-icon{opacity:1}
.props{display:flex;gap:10px;overflow-x:auto;padding:8px 14px 8px;flex-shrink:0}
.prop{flex:0 0 78px;background:#fff;border-radius:12px;padding:8px;text-align:center;
  box-shadow:0 3px 12px rgba(61,43,31,.12)}
.prop img{width:52px;height:52px;object-fit:contain}
.prop div{font-size:11px;color:#6b5848;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hint{text-align:center;font-size:12px;color:#baa994;padding:0 0 14px;flex-shrink:0}
.loading{display:flex;align-items:center;justify-content:center;height:60vw;max-height:540px;font-size:16px;color:#8a7664}
.empty{padding:14px;text-align:center;color:#a99476;font-size:13px}
</style>
</head>
<body>
<div class="header">
  <h1>漫秀Mind Show</h1>
  <p id="story-title"></p>
</div>
<div class="page">
  <div class="summary" id="summary" style="display:none"><span class="label">本幕</span><span id="summary-text"></span></div>
  <div class="deck" id="deck"><div class="loading">加载中…</div></div>
  <div class="counter" id="counter"></div>
  <div class="bubbles" id="bubbles"></div>
</div>
<div class="props" id="props"></div>
<div class="hint">← 左右滑动翻页 · 点气泡重播 →</div>
<script>
const shareId = location.pathname.split("/").pop();
let pages = [], props = [], storyId = "", current = 0;
// 当前页正在 / 即将播放的 audio + bubble 索引
let audioCtl = { audio: null, bubbleEl: null, abort: false, page: -1 };

fetch("/api/share/" + shareId).then(r => r.json()).then(data => {
  storyId = String(data.story_id || "");
  // 后端会保证 pages 存在；老版分享只有 comics，已在 backend 自动包装。
  pages = (data.pages && data.pages.length) ? data.pages
        : (data.comics || []).map(u => ({ comic_url: u, summary: "", storyboard: [] }));
  props = data.props || [];
  document.getElementById("story-title").textContent = data.story_title || "";
  renderProps();
  if (!pages.length) {
    document.getElementById("deck").innerHTML = '<div class="loading">暂无漫画</div>';
    return;
  }
  renderDeck();
  applyPage(0);
}).catch(() => {
  document.getElementById("deck").innerHTML = '<div class="loading">加载失败</div>';
});

function renderProps() {
  const el = document.getElementById("props");
  if (!props.length) { el.style.display = "none"; return; }
  el.innerHTML = props.map(p =>
    `<div class="prop"><img src="${p.url}" alt="${p.name || ""}"/><div>${p.name || ""}</div></div>`
  ).join("");
}

function renderDeck() {
  const deck = document.getElementById("deck");
  deck.innerHTML = "";
  pages.forEach((page, i) => {
    const d = document.createElement("div");
    d.className = "slide";
    const url = page.comic_url || "";
    d.innerHTML = url ? `<img src="${url}" alt="第${i+1}幕"/>` : '<div class="empty">这一幕没有图</div>';
    d.style.zIndex = pages.length - i;
    deck.appendChild(d);
  });
  layoutSlides();
  setupSwipe(deck);
}

function layoutSlides() {
  const slides = document.querySelectorAll(".slide");
  slides.forEach((s, i) => {
    const offset = i - current;
    if (offset < 0) { s.style.transform = "translateX(-120%) scale(0.9)"; s.style.opacity = "0"; }
    else if (offset === 0) { s.style.transform = "translateX(0) scale(1)"; s.style.opacity = "1"; s.style.zIndex = 100; }
    else if (offset <= 2) { s.style.transform = `translateX(${offset*8}px) scale(${1-offset*0.04})`;
      s.style.opacity = String(1 - offset*0.3); s.style.zIndex = 100 - offset; }
    else { s.style.transform = "translateX(24px) scale(0.88)"; s.style.opacity = "0"; s.style.zIndex = 0; }
  });
  document.getElementById("counter").textContent = `${current+1} / ${pages.length}`;
}

function applyPage(i) {
  if (i < 0 || i >= pages.length) return;
  current = i;
  layoutSlides();
  const page = pages[i] || {};
  // summary
  const sumEl = document.getElementById("summary");
  const sumText = document.getElementById("summary-text");
  const sum = String(page.summary || "").trim();
  if (sum) { sumEl.style.display = ""; sumText.textContent = sum; }
  else { sumEl.style.display = "none"; sumText.textContent = ""; }
  // bubbles
  renderBubbles(page.storyboard || []);
  // 自动顺序播放
  stopAudio();
  audioCtl.page = i;
  playAllBubbles(i, 0);
}

function renderBubbles(lines) {
  const wrap = document.getElementById("bubbles");
  wrap.innerHTML = "";
  if (!lines.length) {
    wrap.innerHTML = '<div class="empty">这一幕暂无旁白</div>';
    return;
  }
  lines.forEach((ln, idx) => {
    const div = document.createElement("div");
    const isNarration = (ln.kind === "narration") || (ln.speaker === "旁白");
    div.className = "bubble " + (isNarration ? "narration" : "dialogue");
    div.dataset.idx = String(idx);
    const tone = ln.tone ? `<span class="tone">${escapeHtml(ln.tone)}</span>` : "";
    div.innerHTML =
      `<div class="speaker">${escapeHtml(ln.speaker || "旁白")}${tone}</div>` +
      `<div class="text">${escapeHtml(ln.text || "")}</div>` +
      `<div class="play-icon">🔊</div>`;
    div.addEventListener("click", () => { playBubble(current, idx); });
    wrap.appendChild(div);
  });
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c])
  );
}

function ttsUrl(line) {
  const q = new URLSearchParams({ text: line.text || "" });
  if (line.speaker) q.set("speaker", line.speaker);
  if (line.tone) q.set("tone", line.tone);
  if (line.speaker_gender) q.set("speaker_gender", line.speaker_gender);
  if (storyId) q.set("story_id", storyId);
  return "/api/tts?" + q.toString();
}

function stopAudio() {
  audioCtl.abort = true;
  try { if (audioCtl.audio) { audioCtl.audio.pause(); audioCtl.audio.src = ""; } } catch (e) {}
  audioCtl.audio = null;
  if (audioCtl.bubbleEl) audioCtl.bubbleEl.classList.remove("playing");
  audioCtl.bubbleEl = null;
}

function playOne(pageIdx, bubbleIdx) {
  return new Promise((resolve) => {
    if (pageIdx !== current) return resolve();
    const page = pages[pageIdx] || {};
    const lines = page.storyboard || [];
    const ln = lines[bubbleIdx];
    if (!ln || !ln.text) return resolve();
    const wrap = document.getElementById("bubbles");
    const el = wrap.querySelector(`.bubble[data-idx="${bubbleIdx}"]`);
    audioCtl.abort = false;
    audioCtl.bubbleEl = el || null;
    if (el) el.classList.add("playing");
    const audio = new Audio(ttsUrl(ln));
    audioCtl.audio = audio;
    const cleanup = () => {
      if (el) el.classList.remove("playing");
      if (audioCtl.audio === audio) audioCtl.audio = null;
      audioCtl.bubbleEl = null;
      resolve();
    };
    audio.onended = cleanup;
    audio.onerror = cleanup;
    audio.play().catch(cleanup);
  });
}

async function playAllBubbles(pageIdx, startIdx) {
  const lines = (pages[pageIdx] && pages[pageIdx].storyboard) || [];
  for (let i = startIdx; i < lines.length; i++) {
    if (pageIdx !== current || audioCtl.abort) return;
    await playOne(pageIdx, i);
  }
}

function playBubble(pageIdx, bubbleIdx) {
  // 单个气泡点击重播：停掉自动播放，单条播完即止。
  stopAudio();
  audioCtl.page = pageIdx;
  playOne(pageIdx, bubbleIdx);
}

function setupSwipe(deck) {
  let sx = 0, dx = 0, swiping = false;
  function commit() {
    if (Math.abs(dx) > 50) {
      if (dx < 0 && current < pages.length - 1) applyPage(current + 1);
      else if (dx > 0 && current > 0) applyPage(current - 1);
    }
  }
  deck.addEventListener("touchstart", e => { sx = e.touches[0].clientX; swiping = true; dx = 0; }, {passive:true});
  deck.addEventListener("touchmove", e => { if (!swiping) return; dx = e.touches[0].clientX - sx; }, {passive:true});
  deck.addEventListener("touchend", () => { if (!swiping) return; swiping = false; commit(); });
  deck.addEventListener("mousedown", e => { sx = e.clientX; swiping = true; dx = 0; });
  deck.addEventListener("mousemove", e => { if (!swiping) return; dx = e.clientX - sx; });
  deck.addEventListener("mouseup", () => { if (!swiping) return; swiping = false; commit(); });
}
</script>
</body>
</html>"""


@router.get("/view/{share_id}", response_class=HTMLResponse)
def share_page(share_id: str) -> HTMLResponse:
    p = SHARES_DIR / f"{share_id}.json"
    if not p.exists():
        return HTMLResponse("<h1>分享不存在或已过期</h1>", status_code=404)
    return HTMLResponse(MOBILE_HTML, media_type="text/html; charset=utf-8")
