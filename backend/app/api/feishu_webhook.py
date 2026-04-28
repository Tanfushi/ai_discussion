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
        "cancelled": "已停止",
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
                    {"tag": "button", "text": {"tag": "plain_text", "content": "查看完整讨论"}, "type": "default", "value": {"action": "show_full_report", "task_id": task_id}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "停止讨论"}, "type": "danger", "value": {"action": "stop_task", "task_id": task_id}},
                ],
            },
        ],
    }


def build_expert_selection_card(task_id: str, selected_keys: list[str]) -> dict:
    catalog = expert_catalog()
    options = []
    for key, expert in list(catalog.items()):
        is_easter = key.startswith("easter_")
        role_type = "彩蛋角色🎊" if is_easter else "专家角色"
        options.append(
            {
                "text": {"tag": "plain_text", "content": f"[{role_type}] {expert.name}｜{expert.title}"},
                "value": key,
            }
        )
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
                    "请先在下拉框中一次性勾选专家（3-5位），再点击“开始讨论”。\n"
                    "只有点击提交按钮时才会上传你的选择。\n"
                    "你也可以勾选彩蛋角色（如哆啦A梦🐱、蜡笔小新🖍️）参与讨论，会更可爱更有梗。"
                ),
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "select_static",
                        "name": "expert_keys",
                        "placeholder": {"tag": "plain_text", "content": "请选择参与讨论的专家（可多选）"},
                        "multiple": True,
                        "options": options,
                        "value": selected_keys,
                    },
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


def build_goal_confirmation_card(task_id: str, query: str) -> dict:
    return {
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "先确认一下讨论议题"},
            "subtitle": {"tag": "plain_text", "content": f"任务编号：{task_id[:8]}"},
            "template": "blue",
        },
        "elements": [
            {"tag": "markdown", "content": f"你刚才输入的是：\n\n**{query[:500]}**\n\n这是你想讨论的问题吗？"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "是，进入专家选择"},
                        "type": "primary",
                        "value": {"action": "confirm_goal", "task_id": task_id},
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "不是，重新输入"},
                        "type": "default",
                        "value": {"action": "reject_goal", "task_id": task_id},
                    },
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


def build_live_discussion_card(task_id: str, record) -> dict:
    transcript = record.live_transcript or []
    stage_logs = record.stage_logs or []
    recent_text = "\n".join([f"- {line}" for line in transcript[-15:]]) or "暂无实时发言内容"
    recent_stage = "\n".join([f"- {line}" for line in stage_logs[-6:]]) or "暂无阶段日志"
    status_text = "已停止" if record.cancelled else ("进行中" if record.status == "running" else record.status)
    return {
        "config": {"update_multi": True},
        "header": {
            "title": {"tag": "plain_text", "content": "讨论实时查看"},
            "subtitle": {"tag": "plain_text", "content": f"任务编号：{task_id[:8]}｜状态：{status_text}"},
            "template": "orange",
        },
        "elements": [
            {"tag": "markdown", "content": f"**阶段进度**\n{recent_stage[:1200]}"},
            {"tag": "markdown", "content": f"**实时讨论内容（最近）**\n{recent_text[:2800]}"},
            {
                "tag": "action",
                "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "刷新实时内容"}, "type": "default", "value": {"action": "show_debate", "task_id": task_id}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "查看完整讨论"}, "type": "default", "value": {"action": "show_full_report", "task_id": task_id}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "停止讨论"}, "type": "danger", "value": {"action": "stop_task", "task_id": task_id}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "返回结果摘要"}, "type": "primary", "value": {"action": "back_to_summary", "task_id": task_id}},
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
        latest = repository.get(task_id)
        if latest and latest.cancelled:
            repository.update(task_id, status="cancelled", error="任务已被用户停止")
            if record.message_id:
                feishu_client.patch_message_card(
                    record.message_id,
                    build_progress_card(task_id, "failed", "任务已停止，你可以重新发起新任务。"),
                )
            return

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

    # 先确认用户输入是否真的是讨论议题，避免“你好”也直接开会。
    repository.update(task_id, waiting_goal_confirmation=True, waiting_expert_selection=False, selected_expert_keys=[])
    confirmation_card = build_goal_confirmation_card(task_id, text)
    try:
        message_id = feishu_client.send_card(chat_id, confirmation_card, receive_id_type="chat_id")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send confirmation card: {exc}") from exc
    repository.update(task_id, message_id=message_id)
    return {"ok": True, "task_id": task_id, "waiting_goal_confirmation": True}


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
    if op == "confirm_goal":
        repository.update(task_id, waiting_goal_confirmation=False, waiting_expert_selection=True)
        selection_card = build_expert_selection_card(task_id, record.selected_expert_keys or [])
        try:
            # 用“新发一张卡”替代 patch，规避不同客户端对旧卡更新的兼容问题。
            new_message_id = feishu_client.send_card(record.chat_id, selection_card, receive_id_type="chat_id")
            repository.update(task_id, message_id=new_message_id)
            return {"toast": {"type": "success", "content": "已进入专家选择，请在新卡片中勾选专家。"}}
        except Exception as exc:
            return {"toast": {"type": "error", "content": f"进入专家选择失败：{str(exc)[:120]}"}}

    if op == "reject_goal":
        repository.update(task_id, waiting_goal_confirmation=False, cancelled=True, status="cancelled")
        if record.message_id:
            feishu_client.patch_message_card(
                record.message_id,
                {
                    "config": {"update_multi": True},
                    "header": {
                        "title": {"tag": "plain_text", "content": "已取消本次任务"},
                        "subtitle": {"tag": "plain_text", "content": f"任务编号：{task_id[:8]}"},
                        "template": "grey",
                    },
                    "elements": [
                        {"tag": "markdown", "content": "没问题，请重新发送你真正想讨论的问题，我会先让你确认后再开始。"}
                    ],
                },
            )
        return {"toast": {"type": "info", "content": "已取消，你可以重新输入问题。"}}

    if op == "confirm_experts":
        if record.waiting_goal_confirmation:
            return {"toast": {"type": "warning", "content": "请先确认讨论议题，再选择专家。"}}
        form_value = body.get("event", {}).get("action", {}).get("form_value", {})
        selected_raw = form_value.get("expert_keys", [])
        if isinstance(selected_raw, str):
            selected = [selected_raw]
        elif isinstance(selected_raw, list):
            # 兼容不同卡片组件返回：["expert_1"] 或 [{"value":"expert_1"}]
            selected = []
            for item in selected_raw:
                if isinstance(item, str):
                    selected.append(item)
                elif isinstance(item, dict):
                    value = item.get("value")
                    if isinstance(value, str):
                        selected.append(value)
        else:
            selected = []
        repository.update(task_id, selected_expert_keys=selected)
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
            if record.message_id:
                feishu_client.patch_message_card(record.message_id, build_live_discussion_card(task_id, record))
            return {"toast": {"type": "success", "content": "已切换到实时讨论视图。"}}

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
        # 讨论结束后，细节以“新卡片”展示，保留结果卡不被覆盖。
        detail_card = {
            "config": {"update_multi": True},
            "header": {
                "title": {"tag": "plain_text", "content": "讨论细节摘要"},
                "subtitle": {"tag": "plain_text", "content": f"任务编号：{task_id[:8]}"},
                "template": "purple",
            },
            "elements": [
                {"tag": "markdown", "content": summary[:2600] or "暂无讨论细节"},
            ],
        }
        try:
            feishu_client.send_card(record.chat_id, detail_card, receive_id_type="chat_id")
            return {"toast": {"type": "success", "content": "已发送讨论细节卡片。"}}
        except Exception as exc:
            return {"toast": {"type": "error", "content": f"发送讨论细节卡失败：{str(exc)[:120]}"}}

    if op == "show_full_report":
        if record.message_id and record.result:
            # 讨论完成后，完整讨论以新卡片发送，避免覆盖结果主卡。
            try:
                full_card = build_full_report_card(task_id, record.result)
                feishu_client.send_card(record.chat_id, full_card, receive_id_type="chat_id")
                return {"toast": {"type": "success", "content": "已发送完整讨论卡片。"}}
            except Exception as exc:
                return {"toast": {"type": "error", "content": f"发送完整讨论卡失败：{str(exc)[:120]}"}}
        if record.message_id:
            feishu_client.patch_message_card(record.message_id, build_live_discussion_card(task_id, record))
        return {"toast": {"type": "info", "content": "任务尚未完成，先展示实时讨论内容。"}}

    if op == "back_to_summary":
        if record.message_id and record.result:
            feishu_client.patch_message_card(record.message_id, build_result_card(task_id, record.result))
            return {"toast": {"type": "success", "content": "已返回结果摘要"}}
        if record.message_id:
            latest = repository.get(task_id) or record
            feishu_client.patch_message_card(
                record.message_id,
                build_progress_card(task_id, "discussion", f"任务进行中，已记录 {len(latest.live_transcript or [])} 条实时讨论内容。"),
            )
        return {"toast": {"type": "info", "content": "任务尚未完成，已返回进度卡片。"}}

    if op == "stop_task":
        if record.status in {"completed", "failed", "cancelled"}:
            return {"toast": {"type": "warning", "content": "当前任务已结束，无需停止。"}}
        repository.update(task_id, cancelled=True)
        if record.message_id:
            feishu_client.patch_message_card(
                record.message_id,
                build_progress_card(task_id, "failed", "已收到停止指令，正在终止讨论流程。"),
            )
        return {"toast": {"type": "success", "content": "已发送停止指令，讨论将尽快终止。"}}

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
