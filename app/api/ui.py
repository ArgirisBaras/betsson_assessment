"""Simple web UI for the Email Assistant — served at /ui."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

UI_PATH = Path(__file__).parent / "ui.html"


@router.get("/ui", response_class=HTMLResponse)
async def ui():
    """Serve the Email Assistant web UI."""
    return UI_PATH.read_text(encoding="utf-8")
