"""FastAPI application entry point."""

from __future__ import annotations

import logging
import sys

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stdout,
)

app = FastAPI(
    title="Vorderingsstaten Agent API",
    version="1.7a",
    description="Automated progress-report generation from construction site photos.",
)

# Serve static files (HTML client)
app.mount("/static", StaticFiles(directory="static"), name="static")

from app.api import router  # noqa: E402

app.include_router(router)


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    from app.utils.system_monitor import get_system_resources

    return {"status": "ok", "resources": get_system_resources()}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="localhost", port=8000, reload=True)
