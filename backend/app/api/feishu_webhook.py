import json
from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.integrations.feishu_client import feishu_client
from app.integrations.openai_client import openai_client
from app.config import get_settings
from app.orchestrator.engine import engine
from app.orchestrator.expert_panel import expert_catalog
from app.storage.repository import repository


router = APIRouter(prefix="/api/feishu", tags=["feishu"])


def _stage_cn(stage: str) -> str:
    mapping = {
        "queued": "已受理",
        "planning": "任务拆解",
        "discussion": "多方讨论",
        "judge": "综合裁决",
        "panel_mode": "专家模式",
        "goal_understanding": "目标理解",
        "panel_setup": "专家组建",
        "round_1": "第一回合",
        "round_2": "第二回合",
        "round_3": "第三回合",
        "deep_focus": "深度聚焦",
        "final_report": "报告生成",
        "done": "已完成",
        "failed": "失败",
    }
    return mapping.get(stage, stage)


def build_progress_card(task_id: str, stage: str, detail: str) -> dict:
    return {
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "多机器人协作面板"},
            "subtitle": {"tag": "plain_text", "content": f"任务编号：{task_id[:8]}"},
            "template": "indigo",
        },
        "elements": [
            {"tag": "markdown", "content": f"**当前阶段**：`{_stage_cn(stage)}`\n\n{detail}"},
            {
                "tag": "action",
                "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "重新裁决"}, "type": "default", "value": {"action": "rerun_judge", "task_id": task_id}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "查看讨论细节"}, "type": "default", "value": {"action": "show_debate", "task_id": task_id}},
                ],
            },
        ],
    }


def build_expert_selection_card(task_id: str, selected_keys: list[str]) -> dict:
    catalog = expert_catalog()
    options_md = []
    for key, expert in list(catalog.items())[:8]:
        checked = "☑️" if key in selected_keys else "⬜"
        options_md.append(f"{checked} **{expert.name}**｜{expert.title}")
    picked = len(selected_keys)
    return {
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "请选择参与讨论的专家"},
            "subtitle": {"tag": "plain_text", "content": f"任务编号：{task_id[:8]}（建议选择3-5位，当前{picked}位）"},
            "template": "orange",
        },
        "elements": [
            {
                "tag": "markdown",
                "content": (
                    "请先连续点选专家，系统会先暂存你的选择。\n"
                    "当你点“开始讨论”时，才会一次性提交并启动讨论。\n\n"
                    + "\n".join(options_md)
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "切换：架构师 沈川"},
                        "type": "default",
                        "value": {"action": "toggle_expert", "task_id": task_id, "expert_key": "expert_1"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "切换：安全 顾淮"},
                        "type": "default",
                        "value": {"action": "toggle_expert", "task_id": task_id, "expert_key": "expert_2"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "切换：工程 韩默"},
                        "type": "default",
                        "value": {"action": "toggle_expert", "task_id": task_id, "expert_key": "expert_3"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "切换：SRE 苏砚"},
                        "type": "default",
                        "value": {"action": "toggle_expert", "task_id": task_id, "expert_key": "expert_4"},
                    },
                ],
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "切换：战略 林泽"},
                        "type": "default",
                        "value": {"action": "toggle_expert", "task_id": task_id, "expert_key": "expert_5"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "切换：运营 周岚"},
                        "type": "default",
                        "value": {"action": "toggle_expert", "task_id": task_id, "expert_key": "expert_6"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "切换：投资 赵衡"},
                        "type": "default",
                        "value": {"action": "toggle_expert", "task_id": task_id, "expert_key": "expert_7"},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "切换：财务 许安"},
                        "type": "default",
                        "value": {"action": "toggle_expert", "task_id": task_id, "expert_key": "expert_8"},
                    },
                ],
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "开始讨论（一次性提交）"},
                        "type": "primary",
                        "value": {"action": "confirm_experts", "task_id": task_id},
                    }
                ],
            },
        ],
    }


def build_result_card(task_id: str, result: dict) -> dict:
    if result.get("mode") == "expert_panel":
        experts = result.get("experts", [])
        timeline = result.get("interaction_timeline", [])
        experts_text = "\n".join(
            [
                f"- **{e.get('name','专家')}**｜{e.get('title','')}\n  - 专长：{e.get('expertise','')}\n  - 思维倾向：{e.get('mindset','')}"
                for e in experts[:5]
            ]
        )
        timeline_text = "\n".join(
            [
                f"- 第{t.get('round','?')}轮：**{t.get('from','专家')}** 回应 **{t.get('to','专家')}**（{t.get('point','-')[:36]}）"
                for t in timeline[:8]
            ]
        )
        return {
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": "专家组综合分析报告"},
                "subtitle": {"tag": "plain_text", "content": f"任务编号：{task_id[:8]}"},
                "template": "green",
            },
            "elements": [
                {"tag": "markdown", "content": f"**目标澄清**\n{result.get('objective', '-')[:900]}"},
                {"tag": "markdown", "content": f"**专家阵容（3-5位）**\n{experts_text[:1200]}"},
                {"tag": "markdown", "content": f"**讨论互动时间线（谁回应了谁）**\n{timeline_text[:1200] or '-'}"},
                {"tag": "markdown", "content": f"**深度聚焦与关键分歧**\n{result.get('deep_focus', '-')[:1300]}"},
                {"tag": "markdown", "content": f"**综合分析报告**\n{result.get('final_report', '-')[:2200]}"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看完整讨论"},
                            "type": "primary",
                            "value": {"action": "show_full_report", "task_id": task_id},
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看讨论细节"},
                            "type": "default",
                            "value": {"action": "show_debate", "task_id": task_id},
                        },
                    ],
                },
            ],
        }

    initial = result.get("initial", {})
    return {
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "多机器人任务结果"},
            "subtitle": {"tag": "plain_text", "content": f"任务编号：{task_id[:8]}"},
            "template": "green",
        },
        "elements": [
            {"tag": "markdown", "content": f"**任务拆解**\n{result.get('plan', '-')[:1200]}"},
            {
                "tag": "markdown",
                "content": (
                    f"**研究员观点**\n{initial.get('researcher', '-')[:600]}\n\n"
                    f"**执行者观点**\n{initial.get('executor', '-')[:600]}\n\n"
                    f"**批判者观点**\n{initial.get('critic', '-')[:600]}"
                ),
            },
            {"tag": "markdown", "content": f"**最终裁决**\n{result.get('verdict', '-')[:1800]}"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看完整讨论"},
                        "type": "primary",
                        "value": {"action": "show_full_report", "task_id": task_id},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "查看讨论细节"},
                        "type": "default",
                        "value": {"action": "show_debate", "task_id": task_id},
                    },
                ],
            },
        ],
    }


def build_full_report_card(task_id: str, result: dict) -> dict:
    if result.get("mode") == "expert_panel":
        rounds = result.get("rounds", [])
        timeline = result.get("interaction_timeline", [])
        round_text = []
        for r in rounds[:3]:
            speeches = r.get("speeches", [])
            one_round = "\n\n".join([f"### {s.get('expert','专家')}\n{s.get('content','-')[:500]}" for s in speeches[:5]])
            round_text.append(f"## 第{r.get('round','?')}轮：{r.get('theme','讨论')}\n{one_round}")
        timeline_text = "\n".join(
            [
                f"- 第{t.get('round','?')}轮：{t.get('from','专家')} -> {t.get('to','专家')}｜引用：{t.get('point','-')[:50]}"
                for t in timeline[:20]
            ]
        )
        content = (f"## 互动时间线（谁回应了谁）\n{timeline_text}\n\n" + "\n\n".join(round_text))[:4500]
    else:
        rounds = result.get("rounds", [])
        content = "\n\n".join(
            [
                f"## 第{r['round']}轮\n### 研究员\n{r['researcher'][:500]}\n\n### 执行者\n{r['executor'][:500]}\n\n### 批判者\n{r['critic'][:500]}"
                for r in rounds[:3]
            ]
        )[:4500]

    return {
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "完整讨论记录"},
            "subtitle": {"tag": "plain_text", "content": f"任务编号：{task_id[:8]}"},
            "template": "wathet",
        },
        "elements": [
            {"tag": "markdown", "content": content or "暂无完整讨论记录"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "返回结果摘要"},
                        "type": "primary",
                        "value": {"action": "back_to_summary", "task_id": task_id},
                    }
                ],
            },
        ],
    }


def regenerate_judgement(query: str, result: dict) -> str:
    settings = get_settings()
    if result.get("mode") == "expert_panel":
        prompt = (
            f"主题：{query}\n\n"
            f"目标澄清：{result.get('objective', '-')}\n\n"
            f"深度聚焦：{result.get('deep_focus', '-')}\n\n"
            f"第三轮讨论内容：{result.get('rounds', [])}\n\n"
            "请重新输出裁决结论，结构包含：\n"
            "1) 最终建议（主方案）\n2) 备选方案\n3) 关键风险\n4) 下周可执行动作"
        )
    else:
        prompt = (
            f"任务：{query}\n\n"
            f"任务拆解：{result.get('plan', '-')}\n\n"
            f"讨论轮次：{result.get('rounds', [])}\n\n"
            "请用中文重新做一次综合裁决，结构包含：\n"
            "1) 最终建议\n2) 备选方案\n3) 关键风险\n4) 下一步行动"
        )

    return openai_client.chat(
        messages=[
            {"role": "system", "content": "你是审稿型裁决官，请基于已有讨论进行二次裁决，输出精炼可执行。"},
            {"role": "user", "content": prompt},
        ],
        model=settings.openai_model_judge,
        temperature=0.3,
        max_tokens=900,
        timeout=60,
    )


def _process_task(task_id: str) -> None:
    record = repository.get(task_id)
    if not record:
        return

    def on_stage(stage: str, detail: str) -> None:
        latest = repository.get(task_id)
        if latest:
            logs = list(latest.stage_logs or [])
            logs.append(f"{_stage_cn(stage)}：{detail}")
            repository.update(task_id, stage_logs=logs[-20:])
        if record.message_id:
            feishu_client.patch_message_card(record.message_id, build_progress_card(task_id, stage, detail))

    try:
        result = engine.execute_task(task_id, on_stage=on_stage)
        if record.message_id:
            feishu_client.patch_message_card(record.message_id, build_result_card(task_id, result))
    except Exception as exc:
        repository.update(task_id, status="failed", error=str(exc))
        if record.message_id:
            feishu_client.patch_message_card(
                record.message_id,
                build_progress_card(task_id, "failed", f"任务失败: {exc}"),
            )


@router.post("/webhook")
async def feishu_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()

    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    event = body.get("event", {})
    if body.get("header", {}).get("event_type") != "im.message.receive_v1":
        return {"ok": True}

    message = event.get("message", {})
    if message.get("message_type") != "text":
        return {"ok": True}

    try:
        text = json.loads(message.get("content", "{}")).get("text", "").strip()
    except json.JSONDecodeError:
        text = ""
    if not text:
        return {"ok": True}

    task_id = str(uuid4())
    idempotency_key = message.get("message_id", task_id)
    chat_id = message.get("chat_id", "")

    record = repository.create_or_get(
        task_id=task_id,
        chat_id=chat_id,
        query=text,
        idempotency_key=idempotency_key,
    )

    if record.task_id != task_id:
        return {"ok": True, "task_id": record.task_id, "deduped": True}

    # 默认所有任务都先进入专家选择，确保用户先勾选参与角色再开始讨论。
    repository.update(task_id, waiting_expert_selection=True, selected_expert_keys=[])
    selection_card = build_expert_selection_card(task_id, [])
    try:
        message_id = feishu_client.send_card(chat_id, selection_card, receive_id_type="chat_id")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send selection card: {exc}") from exc
    repository.update(task_id, message_id=message_id)
    return {"ok": True, "task_id": task_id, "waiting_expert_selection": True}


@router.post("/card/callback")
async def card_callback(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    action = body.get("event", {}).get("action", {}).get("value", {})
    task_id = action.get("task_id")
    if not task_id:
        return {}
    record = repository.get(task_id)
    if not record:
        return {"toast": {"type": "error", "content": "任务不存在或已过期"}}

    op = action.get("action")
    if op == "toggle_expert":
        expert_key = action.get("expert_key", "")
        selected = list(record.selected_expert_keys or [])
        if expert_key in selected:
            selected = [k for k in selected if k != expert_key]
        else:
            selected.append(expert_key)
        repository.update(task_id, selected_expert_keys=selected)
        # 点选阶段只做暂存，不刷新整卡，避免“每点一次就传送一次”的感受。
        return {"toast": {"type": "info", "content": f"已暂存，当前选择 {len(selected)} 位。"}}

    if op == "confirm_experts":
        selected = list(record.selected_expert_keys or [])
        if len(selected) < 3:
            return {"toast": {"type": "warning", "content": "请至少选择3位专家再开始讨论。"}}
        if len(selected) > 5:
            return {"toast": {"type": "warning", "content": "最多选择5位专家，请先取消部分勾选。"}}
        repository.update(task_id, waiting_expert_selection=False)
        if record.message_id:
            feishu_client.patch_message_card(
                record.message_id,
                build_progress_card(task_id, "queued", f"已确认 {len(selected)} 位专家，开始进入讨论。"),
            )
        background_tasks.add_task(_process_task, task_id)
        return {"toast": {"type": "success", "content": "专家已确认，正在开始讨论。"}}

    if op == "show_debate":
        if record.status != "completed" and not record.result:
            logs = record.stage_logs or []
            latest_logs = "\n".join([f"- {line}" for line in logs[-8:]])
            return {
                "toast": {
                    "type": "info",
                    "content": (latest_logs[:300] if latest_logs else "任务正在进行中，暂时没有可展示的讨论文本。"),
                }
            }

        rounds = (record.result or {}).get("rounds", [])
        if rounds and isinstance(rounds[0], dict) and "speeches" in rounds[0]:
            chunks = []
            for r in rounds[:2]:
                first_three = r.get("speeches", [])[:3]
                speaker_lines = "\n".join([f"- {s['expert']}: {s['content'][:90]}" for s in first_three])
                chunks.append(f"第{r.get('round', '?')}轮（{r.get('theme', '讨论')}）\n{speaker_lines}")
            timeline = (record.result or {}).get("interaction_timeline", [])
            timeline_hint = "\n".join(
                [
                    f"- 第{t.get('round','?')}轮：{t.get('from','专家')} -> {t.get('to','专家')}"
                    for t in timeline[:4]
                ]
            )
            summary = ("互动关系：\n" + timeline_hint + "\n\n" + "\n\n".join(chunks)).strip()
        else:
            summary = "\n\n".join(
                [
                    f"第{r['round']}轮\n- 研究员：{r['researcher'][:120]}\n- 执行者：{r['executor'][:120]}\n- 批判者：{r['critic'][:120]}"
                    for r in rounds[:2]
                ]
            )
        return {"toast": {"type": "info", "content": summary[:300] or "暂无讨论细节"}}

    if op == "show_full_report":
        if record.message_id and record.result:
            feishu_client.patch_message_card(record.message_id, build_full_report_card(task_id, record.result))
        return {"toast": {"type": "success", "content": "已切换到完整讨论记录"}}

    if op == "back_to_summary":
        if record.message_id and record.result:
            feishu_client.patch_message_card(record.message_id, build_result_card(task_id, record.result))
        return {"toast": {"type": "success", "content": "已返回结果摘要"}}

    if op == "rerun_judge":
        if record.status != "completed" or not record.result:
            return {"toast": {"type": "warning", "content": "当前任务还未完成，暂时不能重新裁决。"}}
        try:
            new_verdict = regenerate_judgement(record.query, record.result)
            result = dict(record.result)
            if result.get("mode") == "expert_panel":
                result["final_report"] = new_verdict
            else:
                result["verdict"] = new_verdict
            repository.update(task_id, result=result)
            if record.message_id:
                feishu_client.patch_message_card(record.message_id, build_result_card(task_id, result))
            return {"toast": {"type": "success", "content": "已完成重新裁决，并更新结果卡片。"}}
        except Exception as exc:
            return {"toast": {"type": "error", "content": f"重新裁决失败：{str(exc)[:120]}"}}

    return {}
