from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from memory.social_graph import SocialGraph
from memory.sqlite import SQLiteMemory


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app(memory: SQLiteMemory) -> FastAPI:
    graph = SocialGraph(memory.database_path)
    app = FastAPI(title="Vozduhan Control Panel")

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        edges = graph.all_edges(limit=30)
        events = graph.all_events(limit=20)
        edge_count = graph.edge_count()
        conflict_count = graph.event_count("conflict")
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "request": request,
                "control": memory.get_control(),
                "states": memory.all_states(),
                "logs": memory.recent_logs(40),
                "graph_edges": edges,
                "graph_events": events,
                "graph_edge_count": edge_count,
                "graph_conflict_count": conflict_count,
            },
        )

    @app.get("/status")
    async def status() -> dict[str, object]:
        control = memory.get_control()
        return {
            "enabled": bool(control["enabled"]),
            "intervention_mode": bool(control["intervention_mode"]),
            "last_response_at": control["last_response_at"],
            "last_response_chat_id": control["last_response_chat_id"],
        }

    @app.post("/toggle")
    async def toggle(enabled: bool | None = None) -> RedirectResponse:
        control = memory.get_control()
        next_value = (not bool(control["enabled"])) if enabled is None else enabled
        memory.set_enabled(next_value)
        return RedirectResponse("/", status_code=303)

    @app.post("/intervention")
    async def intervention(enabled: bool | None = None) -> RedirectResponse:
        control = memory.get_control()
        next_value = (not bool(control["intervention_mode"])) if enabled is None else enabled
        memory.set_intervention_mode(next_value)
        return RedirectResponse("/", status_code=303)

    @app.get("/logs")
    async def logs(limit: int = 100) -> list[dict[str, object]]:
        return memory.recent_logs(limit)

    @app.get("/state")
    async def state() -> list[dict[str, object]]:
        return memory.all_states()

    @app.get("/graph/edges")
    async def graph_edges(limit: int = 50) -> list[dict[str, object]]:
        return graph.all_edges(limit)

    @app.get("/graph/events", response_class=HTMLResponse)
    async def graph_events(limit: int = 20) -> list[dict[str, object]]:
        return graph.all_events(limit)

    return app
