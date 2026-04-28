from app.agents.roles import CRITIC, EXECUTOR, JUDGE, PLANNER, RESEARCHER
from app.config import get_settings
from app.integrations.openai_client import openai_client


def _chat(system: str, user: str, model: str) -> str:
    return openai_client.chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=model,
        temperature=0.4,
        max_tokens=900,
    )


def run_debate(query: str) -> dict:
    settings = get_settings()
    model_planner = settings.openai_model_planner
    model_specialist = settings.openai_model_specialist
    model_judge = settings.openai_model_judge

    plan = _chat(
        PLANNER.system_prompt,
        f"用户任务：\n{query}\n\n请使用中文输出，结构为：任务拆解步骤 + 成功判定标准。",
        model_planner,
    )

    researcher_view = _chat(
        RESEARCHER.system_prompt,
        f"任务：\n{query}\n\n任务拆解：\n{plan}\n\n请用中文输出你的专业观点。",
        model_specialist,
    )
    executor_view = _chat(
        EXECUTOR.system_prompt,
        f"任务：\n{query}\n\n任务拆解：\n{plan}\n\n请用中文输出你的执行建议。",
        model_specialist,
    )
    critic_view = _chat(
        CRITIC.system_prompt,
        f"任务：\n{query}\n\n任务拆解：\n{plan}\n\n请用中文输出你的风险评审。",
        model_specialist,
    )

    round_notes: list[dict[str, str]] = []
    previous = {
        "Researcher": researcher_view,
        "Executor": executor_view,
        "Critic": critic_view,
    }

    for idx in range(settings.max_debate_rounds):
        round_id = idx + 1
        rebuttal_prompt = (
            f"任务：\n{query}\n\n当前观点：\n"
            f"[研究员]\n{previous['Researcher']}\n\n"
            f"[执行者]\n{previous['Executor']}\n\n"
            f"[批判者]\n{previous['Critic']}\n\n"
            "请用中文给出“反驳 + 修正”，控制在8条要点内。"
        )
        previous["Researcher"] = _chat(RESEARCHER.system_prompt, rebuttal_prompt, model_specialist)
        previous["Executor"] = _chat(EXECUTOR.system_prompt, rebuttal_prompt, model_specialist)
        previous["Critic"] = _chat(CRITIC.system_prompt, rebuttal_prompt, model_specialist)
        round_notes.append(
            {
                "round": str(round_id),
                "researcher": previous["Researcher"],
                "executor": previous["Executor"],
                "critic": previous["Critic"],
            }
        )

    judge_input = (
        f"任务：\n{query}\n\n任务拆解：\n{plan}\n\n"
        f"研究员最终观点：\n{previous['Researcher']}\n\n"
        f"执行者最终观点：\n{previous['Executor']}\n\n"
        f"批判者最终观点：\n{previous['Critic']}\n\n"
        "请使用中文输出：\n1) 最终建议\n2) 备选方案\n3) 关键风险\n4) 下一步行动"
    )
    verdict = _chat(JUDGE.system_prompt, judge_input, model_judge)

    return {
        "plan": plan,
        "initial": {
            "researcher": researcher_view,
            "executor": executor_view,
            "critic": critic_view,
        },
        "rounds": round_notes,
        "verdict": verdict,
    }
