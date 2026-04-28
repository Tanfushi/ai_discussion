from fastapi import FastAPI

from app.api.feishu_webhook import router as feishu_router
from app.storage.repository import repository


app = FastAPI(title="Feishu Multi-Agent MVP", version="0.1.0")
app.include_router(feishu_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    record = repository.get(task_id)
    if not record:
        return {"found": False}
    return {
        "found": True,
        "task_id": record.task_id,
        "status": record.status,
        "error": record.error,
        "result": record.result,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
