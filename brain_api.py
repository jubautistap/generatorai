"""
Простой веб-API для мозга: ручные директивы и статус
Запуск: python brain_api.py (или через main.py интегрировать)
"""
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel

from coordinator import AgentCoordinator
from brain import Directive

app = FastAPI()
_coordinator: Optional[AgentCoordinator] = None


class DirectiveIn(BaseModel):
    target_agent: str
    title: str
    description: str


@app.on_event("startup")
async def on_startup():
    global _coordinator
    # В реальном запуске лучше передавать снаружи; для простоты создаём локально
    if _coordinator is None:
        _coordinator = AgentCoordinator()


@app.post("/brain/directives")
async def create_directive(d: DirectiveIn):
    global _coordinator
    if _coordinator is None:
        _coordinator = AgentCoordinator()
    directive = Directive(
        target_agent=d.target_agent,
        title=d.title,
        description=d.description,
        context={}
    )
    await _coordinator.enqueue_directed_task(directive)
    return {"status": "queued"}


@app.get("/status")
async def status():
    global _coordinator
    if _coordinator is None:
        return {"status": "no_active_project"}
    return _coordinator.get_project_status()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("brain_api:app", host="0.0.0.0", port=8080, reload=True)


