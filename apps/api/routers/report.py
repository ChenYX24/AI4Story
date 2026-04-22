import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..config import DASHSCOPE_API_KEY
from ..models import ReportRequest, ReportResponse
from ..services.report_service import build_report

router = APIRouter()


@router.post("/report", response_model=ReportResponse)
def report(req: ReportRequest) -> ReportResponse:
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=424, detail="服务器未配置 DASHSCOPE_API_KEY")
    try:
        payload = build_report(req)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"story {req.story_id!r} not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return ReportResponse(**payload)


# ---------- F8 报告流水线（SSE 骨架）----------
# v2 阶段 1 的简化版：build_report 仍然整体计算，但分阶段流式往前端推 event，
# 前端在每个阶段即时渲染，观感上"边写边出"。真正的 per-scene 提前总结 + LLM 流式
# 在阶段 1 后半段升级（见 ADR-004）。

def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/report/stream")
async def report_stream(req: ReportRequest) -> StreamingResponse:
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=424, detail="服务器未配置 DASHSCOPE_API_KEY")

    async def gen():
        # Stage A: analyze — 按 interactions 数量展开 per-scene 进度
        n_scenes = max(1, len(req.interactions or []))
        yield _sse_event("stage", {"name": "analyze", "label": f"分析互动记录（{n_scenes} 幕）", "state": "running"})
        for i, it in enumerate(req.interactions or [], 1):
            ops_n = len(it.ops or [])
            yield _sse_event("per_scene", {
                "index": i,
                "total": n_scenes,
                "scene_idx": it.scene_idx,
                "ops_n": ops_n,
                "label": f"第 {i}/{n_scenes} 幕 · {ops_n} 个操作",
            })
            await asyncio.sleep(0.12)
        if not req.interactions:
            # 没有交互也发一个 tick，避免用户看到进度条不动
            yield _sse_event("per_scene", {"index": 1, "total": 1, "label": "互动较少，直接总结"})
            await asyncio.sleep(0.15)
        yield _sse_event("stage", {"name": "analyze", "label": "互动记录分析完成", "state": "done"})

        # Stage B: 构建报告 — 调 LLM（会阻塞 2-10s）
        yield _sse_event("stage", {"name": "compose", "label": "撰写三份报告", "state": "running"})
        try:
            # run_in_executor 让同步 build_report 在线程池里跑，不阻塞事件循环
            loop = asyncio.get_running_loop()
            payload = await loop.run_in_executor(None, build_report, req)
        except FileNotFoundError:
            yield _sse_event("error", {"detail": f"story {req.story_id!r} not found", "code": 404})
            return
        except RuntimeError as exc:
            yield _sse_event("error", {"detail": str(exc), "code": 502})
            return
        yield _sse_event("stage", {"name": "compose", "label": "撰写三份报告", "state": "done"})

        # Stage C: 分段流式把三块送出
        # share
        yield _sse_event("chunk", {"kind": "share", "data": payload.get("share") or {}})
        await asyncio.sleep(0.15)
        # kid
        kid = payload.get("kid_section") or {}
        yield _sse_event("chunk", {"kind": "kid_header", "data": {
            "title": kid.get("title", "给你的故事报告"),
            "your_story": kid.get("your_story", ""),
            "original_story": kid.get("original_story", ""),
        }})
        await asyncio.sleep(0.15)
        yield _sse_event("chunk", {"kind": "kid_list", "data": {
            "differences": kid.get("differences", []),
            "questions": kid.get("questions", []),
        }})
        await asyncio.sleep(0.15)
        # parent
        parent = payload.get("parent_section") or {}
        yield _sse_event("chunk", {"kind": "parent_metrics", "data": {
            "title": parent.get("title", "给家长看的观察报告"),
            "metrics": parent.get("metrics", []),
        }})
        await asyncio.sleep(0.15)
        yield _sse_event("chunk", {"kind": "parent_lists", "data": {
            "traits": parent.get("traits", []),
            "weaknesses": parent.get("weaknesses", []),
            "observations": parent.get("observations", []),
            "suggestions": parent.get("suggestions", []),
        }})

        # Stage D: 全部完成 — 附带完整 payload 方便前端一次性收尾
        yield _sse_event("all_done", {"payload": payload})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 防 nginx / cloudflare 缓冲
            "Connection": "keep-alive",
        },
    )
