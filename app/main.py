"""FastAPI application entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stdout,
)


class SuppressProgressPollFilter(logging.Filter):
    """Hide noisy progress polling access logs while keeping app milestones visible."""

    def filter(self, record: logging.LogRecord) -> bool:
        return '"GET /progress/' not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(SuppressProgressPollFilter())

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLASSIC_FRONTEND = PROJECT_ROOT / "static" / "index.html"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"
FRONTEND_MODE_ENV = "VORDERINGSSTATEN_FRONTEND_MODE"


def _frontend_mode(frontend_mode: str | None = None) -> str:
    mode = (frontend_mode or os.getenv(FRONTEND_MODE_ENV, "v2")).strip().lower()
    return "classic" if mode in {"classic", "old", "old-frontend"} else "v2"


def _frontend_dist_file(full_path: str) -> Path | None:
    """Resolve a built frontend file under FRONTEND_DIST, rejecting path traversal."""
    if not full_path or full_path.startswith(("/", "\\")) or ".." in Path(full_path).parts:
        return None
    dist_root = FRONTEND_DIST.resolve()
    candidate = (dist_root / full_path).resolve()
    try:
        candidate.relative_to(dist_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _missing_frontend_response() -> HTMLResponse:
    return HTMLResponse(
        status_code=503,
        content=(
            "<!doctype html><html><head><title>V2 frontend build missing</title></head>"
            "<body style='font-family: system-ui; max-width: 760px; margin: 48px auto;'>"
            "<h1>V2 frontend build missing</h1>"
            "<p>The React v2 frontend is the default UI, but <code>frontend/dist/index.html</code> "
            "does not exist yet.</p>"
            "<p>Build it first:</p>"
            "<pre>cd frontend\nnpm install\nnpm run build\ncd ..\npython -m app.main</pre>"
            "<p>To use the classic UI without building v2, run "
            "<code>python -m app.main --old-frontend</code>.</p>"
            "</body></html>"
        ),
    )


def _v2_frontend_response() -> FileResponse | HTMLResponse:
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return _missing_frontend_response()


def create_app(frontend_mode: str | None = None) -> FastAPI:
    selected_frontend = _frontend_mode(frontend_mode)
    fastapi_app = FastAPI(
        title="Vorderingsstaten Agent API",
        version="1.9",
        description="Automated progress-report generation from construction site photos and timelapses.",
    )

    fastapi_app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
    if (FRONTEND_DIST / "assets").exists():
        fastapi_app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIST / "assets"),
            name="frontend_assets",
        )

    from app.api import router  # noqa: WPS433

    fastapi_app.include_router(router)

    @fastapi_app.get("/health")
    async def health():
        from app.utils.system_monitor import get_system_resources

        return {"status": "ok", "resources": get_system_resources()}

    @fastapi_app.get("/classic")
    async def classic_frontend():
        return FileResponse(CLASSIC_FRONTEND)

    @fastapi_app.get("/v2")
    async def v2_frontend():
        return _v2_frontend_response()

    @fastapi_app.get("/")
    async def root():
        if selected_frontend == "classic":
            return FileResponse(CLASSIC_FRONTEND)
        return _v2_frontend_response()

    @fastapi_app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if selected_frontend == "classic":
            return FileResponse(CLASSIC_FRONTEND)
        dist_file = _frontend_dist_file(full_path)
        if dist_file is not None:
            return FileResponse(dist_file)
        if "." in Path(full_path).name:
            return _missing_frontend_response()
        return _v2_frontend_response()

    return fastapi_app


app = create_app()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Vorderingsstaten Agent API.")
    parser.add_argument(
        "--old-frontend",
        action="store_true",
        help="Serve the classic static/index.html UI at / instead of the v2 React frontend.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    if args.old_frontend:
        os.environ[FRONTEND_MODE_ENV] = "classic"
    else:
        os.environ.pop(FRONTEND_MODE_ENV, None)
    uvicorn.run("app.main:app", host="localhost", port=8000, reload=True)
