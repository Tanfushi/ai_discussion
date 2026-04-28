from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Callable

from app.config import get_settings
from app.orchestrator.debate import run_debate
from app.orchestrator.expert_panel import run_expert_panel, should_use_expert_panel
from app.storage.repository import repository


StageCallback = Callable[[str, str], None]


class OrchestratorEngine:
    def __init__(self) -> None:
        self.settings = get_settings()

    def execute_task(self, task_id: str, on_stage: StageCallback | None = None) -> dict:
        record = repository.get(task_id)
        if not record:
            raise ValueError(f"Task not found: {task_id}")

        repository.update(task_id, status="running")
        use_expert_panel = should_use_expert_panel(record.query)
        if on_stage:
            if use_expert_panel:
                on_stage("panel_mode", "检测到深度分析目标，切换到专家组深度讨论模式。")
            else:
                on_stage("planning", "正在拆解任务并定义评估标准。")

        with ThreadPoolExecutor(max_workers=1) as pool:
            if use_expert_panel:
                future = pool.submit(
                    run_expert_panel,
                    record.query,
                    on_stage,
                    record.selected_expert_keys,
                )
            else:
                future = pool.submit(run_debate, record.query)
            try:
                if on_stage:
                    if not use_expert_panel:
                        on_stage("discussion", "各角色正在讨论方案利弊与权衡。")
                result = future.result(timeout=self.settings.task_timeout_seconds)
            except FuturesTimeoutError as exc:
                repository.update(
                    task_id,
                    status="failed",
                    error=f"Task timeout after {self.settings.task_timeout_seconds}s",
                )
                raise TimeoutError("Orchestration timeout") from exc
            except Exception as exc:
                retries = (record.retries or 0) + 1
                repository.update(task_id, status="failed", retries=retries, error=str(exc))
                raise

        repository.update(task_id, status="completed", result=result, error=None)
        if on_stage:
            if use_expert_panel:
                on_stage("done", "专家组讨论完成，正在展示综合报告。")
            else:
                on_stage("judge", "综合裁决已完成，正在整理最终建议。")
        return result


engine = OrchestratorEngine()
