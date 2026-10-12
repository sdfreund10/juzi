from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse


def spa(request: HttpRequest) -> HttpResponse:
    """Serve the Preact index.html for non-API routes (same-origin SPA)."""
    index = Path(settings.FRONTEND_DIST) / "index.html"
    if not index.is_file():
        raise Http404(
            "Frontend build not found. Run `npm run build` or `npm run dev` in frontend/."
        )
    return FileResponse(index.open("rb"), content_type="text/html")
