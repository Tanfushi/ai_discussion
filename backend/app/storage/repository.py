from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class TaskRecord:
    task_id: str
    chat_id: str
    query: str
    initiator_open_id: str = ""
    status: str = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    message_id: str | None = None
    idempotency_key: str | None = None
    retries: int = 0
    stage_logs: list[str] = field(default_factory=list)
    selected_expert_keys: list[str] = field(default_factory=list)
    selection_page: int = 0
    waiting_goal_confirmation: bool = False
    waiting_expert_selection: bool = False
    cancelled: bool = False
    live_transcript: list[str] = field(default_factory=list)
    ui_view_mode: str = "progress"
    vote_up: int = 0
    vote_down: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._idempotency_index: dict[str, str] = {}
        self._lock = Lock()

    def create_or_get(
        self,
        task_id: str,
        chat_id: str,
        query: str,
        idempotency_key: str,
        initiator_open_id: str = "",
    ) -> TaskRecord:
        with self._lock:
            exists_id = self._idempotency_index.get(idempotency_key)
            if exists_id and exists_id in self._tasks:
                return self._tasks[exists_id]

            record = TaskRecord(
                task_id=task_id,
                chat_id=chat_id,
                query=query,
                idempotency_key=idempotency_key,
                initiator_open_id=initiator_open_id,
            )
            self._tasks[task_id] = record
            self._idempotency_index[idempotency_key] = task_id
            return record

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs: Any) -> TaskRecord | None:
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return None
            for key, value in kwargs.items():
                setattr(record, key, value)
            record.updated_at = datetime.now(timezone.utc).isoformat()
            return record

    def add_vote(self, task_id: str, vote_type: str) -> TaskRecord | None:
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return None
            if vote_type == "up":
                record.vote_up += 1
            elif vote_type == "down":
                record.vote_down += 1
            record.updated_at = datetime.now(timezone.utc).isoformat()
            return record

    def get_recent_by_chat(self, chat_id: str, limit: int = 5) -> list[TaskRecord]:
        with self._lock:
            records = [t for t in self._tasks.values() if t.chat_id == chat_id and t.status in {"completed", "cancelled", "failed"}]
            records.sort(key=lambda t: t.updated_at, reverse=True)
            return records[:limit]

    def get_previous_completed(self, chat_id: str, exclude_task_id: str | None = None) -> TaskRecord | None:
        with self._lock:
            records = [
                t
                for t in self._tasks.values()
                if t.chat_id == chat_id and t.status == "completed" and (exclude_task_id is None or t.task_id != exclude_task_id)
            ]
            records.sort(key=lambda t: t.updated_at, reverse=True)
            return records[0] if records else None


repository = TaskRepository()
