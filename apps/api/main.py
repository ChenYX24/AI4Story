from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIR, OUTPUTS_ROOT, SCENES_DIR
from .routers import chat, create_prop, interact, placements, report, share, stories, story, tts


def create_app() -> FastAPI:
    app = FastAPI(title="AI4Story Web Demo", version="0.1.0")

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

    @app.get("/view/{share_id}")
    def share_view_page(share_id: str) -> HTMLResponse:
        result = share.share_page(share_id)
        # share_page returns an HTMLResponse object; pass it through directly
        return result

    app.mount("/assets/scenes", StaticFiles(directory=SCENES_DIR), name="scenes")
    app.mount("/outputs", StaticFiles(directory=OUTPUTS_ROOT), name="outputs")
    app.mount(
        "/static",
        StaticFiles(directory=FRONTEND_DIR),
        name="frontend_static",
    )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app


app = create_app()
