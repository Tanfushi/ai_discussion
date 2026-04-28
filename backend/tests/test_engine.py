from app.orchestrator.engine import OrchestratorEngine
from app.storage.repository import repository


def test_execute_task_success(monkeypatch):
    task_id = "task-engine-success"
    repository.create_or_get(task_id, "chat-1", "build plan", "msg-engine-success")

    def fake_run_debate(query: str):
        return {"plan": "p", "initial": {}, "rounds": [], "verdict": f"ok:{query}"}

    monkeypatch.setattr("app.orchestrator.engine.run_debate", fake_run_debate)
    engine = OrchestratorEngine()
    result = engine.execute_task(task_id)
    assert "verdict" in result
    assert repository.get(task_id).status == "completed"


def test_execute_task_expert_panel_mode(monkeypatch):
    task_id = "task-expert-panel"
    repository.create_or_get(task_id, "chat-2", "请做多角度深度分析与专家讨论", "msg-expert-panel")

    def fake_run_expert(query: str, on_stage=None, selected_expert_keys=None):
        if on_stage:
            on_stage("round_1", "ok")
        return {"mode": "expert_panel", "final_report": f"report:{query}", "rounds": []}

    monkeypatch.setattr("app.orchestrator.engine.should_use_expert_panel", lambda _q: True)
    monkeypatch.setattr("app.orchestrator.engine.run_expert_panel", fake_run_expert)
    engine = OrchestratorEngine()
    result = engine.execute_task(task_id)
    assert result["mode"] == "expert_panel"
    assert repository.get(task_id).status == "completed"
