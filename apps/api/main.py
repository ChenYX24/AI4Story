from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import APPS_DIR, FRONTEND_DIR, OUTPUTS_ROOT, SCENES_DIR
from .routers import (
    asset_packs,
    auth,
    chat,
    create_prop,
    interact,
    placements,
    public,
    report,
    share,
    stories,
    story,
    tts,
    upload,
    user_assets,
)


def create_app() -> FastAPI:
    app = FastAPI(title="AI4Story Web Demo", version="0.2.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(story.router, prefix="/api")
    app.include_router(tts.router, prefix="/api")
    app.include_router(interact.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(placements.router, prefix="/api")
    app.include_router(create_prop.router, prefix="/api")
    app.include_router(stories.router, prefix="/api")
    app.include_router(report.router, prefix="/api")
    app.include_router(share.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    app.include_router(upload.router, prefix="/api")
    app.include_router(user_assets.router, prefix="/api")
    app.include_router(asset_packs.router, prefix="/api")

    @app.get("/view/{share_id}")
    def share_view_page(share_id: str) -> HTMLResponse:
        return share.share_page(share_id)

    app.mount("/assets/scenes", StaticFiles(directory=SCENES_DIR), name="scenes")
    app.mount("/outputs", StaticFiles(directory=OUTPUTS_ROOT), name="outputs")

    # ---- 前端静态：v2 是 Vite/Vue 的 dist；如不存在退回 web-legacy（原生 JS） ----
    web_v2_dist = APPS_DIR / "web" / "dist"
    web_legacy = APPS_DIR / "web-legacy"
    if web_v2_dist.exists():
        # Vite 把 hashed 资产输出到 dist/bundle/
        bundle_dir = web_v2_dist / "bundle"
        if bundle_dir.exists():
            app.mount("/bundle", StaticFiles(directory=bundle_dir), name="bundle")
        # 旧 /static 路径：兼容 share 页面 / legacy（如还有人引用）
        if web_legacy.exists():
            app.mount("/static", StaticFiles(directory=web_legacy), name="legacy_static")
        spa_index = web_v2_dist / "index.html"
    else:
        # 旧路径退回
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="frontend_static")
        spa_index = FRONTEND_DIR / "index.html"

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/server-info")
    def server_info() -> dict:
        # 用本地 IP 探测 (best effort)
        import socket
        lan_ip = ""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass
        return {"lan_ip": lan_ip}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(spa_index)

    # SPA fallback：先看 dist 下是否有该文件（favicon/manifest 等），没有才回 index.html 让 vue-router 接管
    _dist_root = web_v2_dist if web_v2_dist.exists() else FRONTEND_DIR

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request) -> FileResponse:
        _ = request  # unused
        if full_path:
            cand = _dist_root / full_path
            try:
                if cand.is_file() and cand.resolve().is_relative_to(_dist_root.resolve()):
                    return FileResponse(cand)
            except (ValueError, OSError):
                pass
        return FileResponse(spa_index)

    return app


app = create_app()
