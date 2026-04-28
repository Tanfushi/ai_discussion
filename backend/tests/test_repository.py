from app.storage.repository import TaskRepository


def test_idempotency_create_or_get():
    repo = TaskRepository()
    t1 = repo.create_or_get("task-1", "chat-1", "hello", "msg-1")
    t2 = repo.create_or_get("task-2", "chat-1", "hello", "msg-1")
    assert t1.task_id == t2.task_id
    assert t2.task_id == "task-1"
