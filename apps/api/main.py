from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import APPS_DIR, OUTPUTS_ROOT, SCENES_DIR
from .routers import (
    asset_packs,
    auth,
    chat,
    create_prop,
    interact,
    placements,
    public,
    report,
    sessions,
    share,
    stories,
    story,
    tts,
    upload,
    user_assets,
    video_import,
)


FRONTEND_MISSING_HTML = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>AI4Story frontend is not built</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 48px; line-height: 1.5; }
      code { background: #f4f0e8; padding: 2px 6px; border-radius: 6px; }
    </style>
  </head>
  <body>
    <h1>AI4Story frontend is not built</h1>
    <p>The legacy frontend is intentionally disabled. Build the current Vue app first:</p>
    <p><code>cd apps/web &amp;&amp; pnpm install &amp;&amp; pnpm build</code></p>
    <p>For development, open the Vite dev server started by <code>start_webdemo.cmd</code>.</p>
  </body>
</html>
"""


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
    app.include_router(sessions.router, prefix="/api")
    app.include_router(video_import.router, prefix="/api")

    @app.get("/view/{share_id}")
    def share_view_page(share_id: str) -> HTMLResponse:
        return share.share_page(share_id)

    app.mount("/assets/scenes", StaticFiles(directory=SCENES_DIR), name="scenes")
    app.mount("/outputs", StaticFiles(directory=OUTPUTS_ROOT), name="outputs")

    web_v2_dist = APPS_DIR / "web" / "dist"
    web_legacy = APPS_DIR / "web-legacy"
    spa_index = None
    dist_root = None

    # Serve the current Vite/Vue app only. Do not silently fall back to legacy UI.
    if web_v2_dist.exists():
        bundle_dir = web_v2_dist / "bundle"
        if bundle_dir.exists():
            app.mount("/bundle", StaticFiles(directory=bundle_dir), name="bundle")
        if web_legacy.exists():
            app.mount("/static", StaticFiles(directory=web_legacy), name="legacy_static")
        spa_index = web_v2_dist / "index.html"
        dist_root = web_v2_dist

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/server-info")
    def server_info() -> dict:
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
    def index():
        if spa_index is None:
            return HTMLResponse(FRONTEND_MISSING_HTML, status_code=503)
        return FileResponse(spa_index)

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str, request: Request):
        _ = request  # unused
        if spa_index is None or dist_root is None:
            return HTMLResponse(FRONTEND_MISSING_HTML, status_code=503)
        if full_path:
            cand = dist_root / full_path
            try:
                if cand.is_file() and cand.resolve().is_relative_to(dist_root.resolve()):
                    return FileResponse(cand)
            except (ValueError, OSError):
                pass
        return FileResponse(spa_index)

    return app


app = create_app()
