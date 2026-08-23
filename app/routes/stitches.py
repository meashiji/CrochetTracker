from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.stitches import STITCHES

router = APIRouter(prefix="/stitches")
templates = Jinja2Templates(directory="app/templates")


@router.get("/panel")
async def stitch_panel(request: Request):
    """Serve the stitch reference panel fragment (US notation).

    Read-only static content carrying no user data, so the middleware lists
    the path as public and the panel also works on logged-out pages.

    Returns:
        TemplateResponse: the panel fragment with all stitches rendered.
    """
    return templates.TemplateResponse(
        request, "stitches/_panel.html", {"stitches": STITCHES}
    )
