"""JSON with an explicit charset. Windows PowerShell 5.1 guesses Latin-1 without one and garbles curly apostrophes."""

from __future__ import annotations

from fastapi.responses import JSONResponse


class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"
