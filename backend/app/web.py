"""Serve the built React app from the API process (single-container deployments)."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

# Paths the SPA must never answer: unknown API routes keep their JSON 404.
_BACKEND_PREFIXES = ("api/", "ws", "docs", "redoc", "openapi.json")


def mount_frontend(app: FastAPI, directory: Path) -> None:
    root = directory.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"static_dir {root} has no index.html; build the frontend first")

    # Hashed bundles never change, so browsers may keep them for a year.
    app.mount("/assets", _ImmutableStaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith(_BACKEND_PREFIXES):
            raise HTTPException(status_code=404)
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            return FileResponse(file)  # favicon.svg and other files in public/
        # Client-side routes (/rfqs/:id, /rfqs/new, …) all load the app shell.
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


class _ImmutableStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
