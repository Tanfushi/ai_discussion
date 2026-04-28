from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Callable

from app.config import get_settings
from app.integrations.openai_client import openai_client


StageCallback = Callable[[str, str], None]
TranscriptCallback = Callable[[str], None]
StopCallback = Callable[[], bool]

TRIGGER_KEYWORDS = [
    "深度分析",
    "专家讨论",
    "多角度分析",
    "专家评审",
    "圆桌讨论",
    "集思广益",
    "从多个角度分析",
    "帮我深入研究",
    "全面评估",
    "专家意见",
]


@dataclass
class ExpertProfile:
    name: str
    title: str
    expertise: str
    background: str
    mindset: str


def expert_catalog() -> dict[str, ExpertProfile]:
    experts = {
        "expert_1": ExpertProfile("沈川", "首席架构师（互联网公司）", "系统架构、性能、可扩展性", "主导过大规模高并发系统重构。", "优先关注复杂度与长期演进"),
        "expert_2": ExpertProfile("顾淮", "安全与合规负责人（安全团队）", "应用安全、数据合规、审计", "长期负责企业级安全体系建设。", "先保底线，再谈效率"),
        "expert_3": ExpertProfile("韩默", "工程效能负责人（研发组织）", "交付流程、工程管理、质量", "擅长从工程流程角度提升交付成功率。", "强调迭代速度与稳定平衡"),
        "expert_4": ExpertProfile("苏砚", "SRE负责人（平台团队）", "可观测性、容灾、运维治理", "长期维护核心生产系统稳定性。", "优先评估故障模式与运维成本"),
        "expert_5": ExpertProfile("林泽", "战略咨询合伙人（咨询机构）", "战略、竞争、组织执行", "长期服务平台与企业服务客户，擅长战略落地。", "自上而下，先判断长期壁垒"),
        "expert_6": ExpertProfile("周岚", "行业运营负责人（头部平台）", "业务运营、渠道、商业化", "20年行业经验，关注一线执行约束。", "强调可落地和短中期收益"),
        "expert_7": ExpertProfile("赵衡", "风险投资合伙人（VC）", "商业模式、增长效率、资本约束", "聚焦成长型公司的资源配置效率。", "偏好高杠杆增长与可验证路径"),
        "expert_8": ExpertProfile("许安", "财务与风控专家（企业财务）", "预算、ROI、风险控制", "负责过多项数字化转型项目的财务评审。", "重视现金流、安全边界与合规"),
        "expert_9": ExpertProfile("程霁", "产品战略总监（互联网产品）", "产品定位、增长策略", "多次主导从0到1产品孵化。", "强调市场窗口和差异化"),
        "expert_10": ExpertProfile("莫青", "用户研究负责人（体验团队）", "用户洞察、行为研究", "长期研究用户决策路径。", "从用户动机反推方案优先级"),
        "expert_11": ExpertProfile("袁潇", "交互设计专家（设计团队）", "信息架构、关键路径体验", "聚焦复杂产品的体验简化。", "关注认知负荷与转化路径"),
        "expert_12": ExpertProfile("魏临", "数据分析负责人（数据团队）", "指标体系、实验设计、归因", "负责增长实验和策略评估。", "以数据证据校验假设"),
        "expert_13": ExpertProfile("陈汀", "政策研究员（智库）", "政策解读、监管趋势", "长期跟踪产业政策与监管演进。", "优先看政策边界与可预期性"),
        "expert_14": ExpertProfile("高奕", "社会学研究者（研究机构）", "社会影响、行为变迁", "研究技术变革对群体行为影响。", "关注长期社会外部性"),
        "expert_15": ExpertProfile("罗旻", "宏观经济分析师（研究院）", "宏观周期、产业经济", "擅长从宏观视角评估政策效果。", "强调系统性影响与传导路径"),
        "expert_16": ExpertProfile("唐屿", "技术伦理顾问（伦理委员会）", "伦理治理、价值冲突", "参与多项AI伦理治理项目。", "先审视不可逆风险"),
        "easter_doraemon": ExpertProfile("哆啦A梦🐱", "22世纪的机器猫（彩蛋角色）", "创意道具、逆向思维、儿童教育视角", "来自22世纪，擅长用未来道具和想象力拆解复杂问题。", "先找更聪明的解法，再看现实约束"),
        "easter_shinchan": ExpertProfile("蜡笔小新🖍️", "春日部向日葵B班核心成员（彩蛋角色）", "用户直觉、场景吐槽、行为观察", "以孩童视角戳穿伪需求和复杂术语，经常一针见血。", "先问好不好玩、好不好懂、好不好用"),
        "easter_konan": ExpertProfile("江户川柯南🕵️", "平成时代的福尔摩斯（彩蛋角色）", "证据链、因果推断、风险排查", "擅长从细节中找关键矛盾并还原完整事实链。", "先锁定事实，再还原真相"),
    }
    return experts


def experts_by_keys(keys: list[str]) -> list[ExpertProfile]:
    catalog = expert_catalog()
    return [catalog[k] for k in keys if k in catalog]


def should_use_expert_panel(query: str) -> bool:
    text = query.strip().lower()
    if any(k in query for k in TRIGGER_KEYWORDS):
        return True

    complex_signals = ["分析", "评估", "方案", "决策", "风险", "比较", "权衡", "战略", "架构"]
    depth_signals = ["深入", "全面", "系统", "多角度", "全方位", "论证"]
    return any(s in query for s in complex_signals) and any(s in query for s in depth_signals)


def _chat(system: str, user: str, model: str, max_tokens: int = 1200) -> str:
    return openai_client.chat(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=model,
        temperature=0.5,
        max_tokens=max_tokens,
        timeout=60,
    )


def _detect_domain(query: str) -> str:
    if any(k in query for k in ["系统", "架构", "技术", "代码", "工程", "AI", "模型", "部署"]):
        return "tech"
    if any(k in query for k in ["产品", "用户", "体验", "功能", "增长"]):
        return "product"
    if any(k in query for k in ["政策", "监管", "法规", "治理", "社会"]):
        return "policy"
    return "business"


def _default_experts(domain: str) -> list[ExpertProfile]:
    pools: dict[str, list[ExpertProfile]] = {
        "business": [
            ExpertProfile("林泽", "战略咨询合伙人（咨询机构）", "战略、竞争、组织执行", "长期服务平台与企业服务客户，擅长战略落地。", "自上而下，先判断长期壁垒"),
            ExpertProfile("周岚", "行业运营负责人（头部平台）", "业务运营、渠道、商业化", "20年行业经验，关注一线执行约束。", "强调可落地和短中期收益"),
            ExpertProfile("赵衡", "风险投资合伙人（VC）", "商业模式、增长效率、资本约束", "聚焦成长型公司的资源配置效率。", "偏好高杠杆增长与可验证路径"),
            ExpertProfile("许安", "财务与风控专家（企业财务）", "预算、ROI、风险控制", "负责过多项数字化转型项目的财务评审。", "重视现金流、安全边界与合规"),
        ],
        "tech": [
            ExpertProfile("沈川", "首席架构师（互联网公司）", "系统架构、性能、可扩展性", "主导过大规模高并发系统重构。", "优先关注复杂度与长期演进"),
            ExpertProfile("顾淮", "安全与合规负责人（安全团队）", "应用安全、数据合规、审计", "长期负责企业级安全体系建设。", "先保底线，再谈效率"),
            ExpertProfile("韩默", "工程效能负责人（研发组织）", "交付流程、工程管理、质量", "擅长从工程流程角度提升交付成功率。", "强调迭代速度与稳定平衡"),
            ExpertProfile("苏砚", "SRE负责人（平台团队）", "可观测性、容灾、运维治理", "长期维护核心生产系统稳定性。", "优先评估故障模式与运维成本"),
        ],
        "product": [
            ExpertProfile("程霁", "产品战略总监（互联网产品）", "产品定位、增长策略", "多次主导从0到1产品孵化。", "强调市场窗口和差异化"),
            ExpertProfile("莫青", "用户研究负责人（体验团队）", "用户洞察、行为研究", "长期研究用户决策路径。", "从用户动机反推方案优先级"),
            ExpertProfile("袁潇", "交互设计专家（设计团队）", "信息架构、关键路径体验", "聚焦复杂产品的体验简化。", "关注认知负荷与转化路径"),
            ExpertProfile("魏临", "数据分析负责人（数据团队）", "指标体系、实验设计、归因", "负责增长实验和策略评估。", "以数据证据校验假设"),
        ],
        "policy": [
            ExpertProfile("陈汀", "政策研究员（智库）", "政策解读、监管趋势", "长期跟踪产业政策与监管演进。", "优先看政策边界与可预期性"),
            ExpertProfile("高奕", "社会学研究者（研究机构）", "社会影响、行为变迁", "研究技术变革对群体行为影响。", "关注长期社会外部性"),
            ExpertProfile("罗旻", "宏观经济分析师（研究院）", "宏观周期、产业经济", "擅长从宏观视角评估政策效果。", "强调系统性影响与传导路径"),
            ExpertProfile("唐屿", "技术伦理顾问（伦理委员会）", "伦理治理、价值冲突", "参与多项AI伦理治理项目。", "先审视不可逆风险"),
        ],
    }
    return pools[domain][:4]


def _build_expert_panel(query: str, model: str) -> list[ExpertProfile]:
    domain = _detect_domain(query)
    defaults = _default_experts(domain)
    seed = [asdict(e) for e in defaults]
    prompt = (
        "基于用户目标，在以下候选专家基础上做轻微调整，输出3-5位互补专家。\n"
        "要求JSON数组，每个元素字段: name,title,expertise,background,mindset。\n"
        f"用户目标:\n{query}\n\n候选专家:\n{json.dumps(seed, ensure_ascii=False)}"
    )
    try:
        raw = _chat("你是专家组组建助手，只输出JSON。", prompt, model, max_tokens=900)
        start = raw.find("[")
        end = raw.rfind("]")
        panel = json.loads(raw[start : end + 1])
        experts = [
            ExpertProfile(
                name=p["name"],
                title=p["title"],
                expertise=p["expertise"],
                background=p["background"],
                mindset=p["mindset"],
            )
            for p in panel[:5]
        ]
        return experts if len(experts) >= 3 else defaults
    except Exception:
        return defaults


def run_expert_panel(
    query: str,
    on_stage: StageCallback | None = None,
    selected_expert_keys: list[str] | None = None,
    on_transcript: TranscriptCallback | None = None,
    should_stop: StopCallback | None = None,
) -> dict:
    settings = get_settings()
    model_planner = settings.openai_model_planner
    model_specialist = settings.openai_model_specialist
    model_judge = settings.openai_model_judge

    if on_stage:
        on_stage("goal_understanding", "正在解析你的目标与分析范围。")
    if should_stop and should_stop():
        raise RuntimeError("任务已被用户停止")

    objective = _chat(
        "你是分析任务澄清助手。",
        f"请提炼用户目标，输出：核心问题/分析深度/关键视角/期望输出。\n\n用户输入:\n{query}",
        model_planner,
        max_tokens=600,
    )

    if on_stage:
        on_stage("panel_setup", "正在组建3-5位互补专家。")
    experts = experts_by_keys(selected_expert_keys or [])
    if len(experts) < 3:
        auto_experts = _build_expert_panel(query, model_planner)
        existing_names = {e.name for e in experts}
        for auto_expert in auto_experts:
            if auto_expert.name not in existing_names:
                experts.append(auto_expert)
                existing_names.add(auto_expert.name)
            if len(experts) >= 3:
                break
    if on_transcript:
        on_transcript("【系统】已确认专家阵容：" + "、".join([e.name for e in experts]))

    interaction_timeline: list[dict[str, str]] = []

    def _extract_reference(content: str) -> tuple[str, str]:
        target = "未指定"
        point = "未提取到明确引用"
        m_target = re.search(r"引用对象[:：]\s*([^\n]+)", content)
        if m_target:
            target = m_target.group(1).strip()
        m_point = re.search(r"引用观点[:：]\s*([^\n]+)", content)
        if m_point:
            point = m_point.group(1).strip()
        return target, point

    def round_speech(round_no: int, expert: ExpertProfile, context: str) -> str:
        is_easter = "彩蛋角色" in expert.title
        if round_no == 1:
            instruction = (
                "请以第一人称输出150-300字发言，并追加：\n"
                "📌 核心立场: ...\n⚡ 关键关注点:\n- ...\n- ..."
            )
        elif round_no == 2:
            instruction = (
                "你在专家交叉质询回合。必须明确引用一位其他专家并回应，格式必须包含：\n"
                "引用对象：<专家名>\n"
                "引用观点：<对方某个观点>\n"
                "我的回应：<你的反驳/补充>\n"
                "并继续给出修正建议，总字数150-260字。"
            )
        else:
            instruction = (
                "你在综合建议回合。必须先引用一位专家并说明你采纳/反对了什么，再给出："
                "最终判断（允许修正）、1-2条具体建议、关键风险。格式必须包含：\n"
                "引用对象：<专家名>\n"
                "引用观点：<对方某个观点>\n"
                "我的综合判断：<你的结论>\n"
                "总字数150-260字。"
            )
        style_hint = (
            "你是彩蛋角色，请使用更可爱、更有梗的语气，适度多用表情符号（例如😊✨🎉🤔），"
            "但仍要给出有用、可执行的观点，避免只卖萌。"
            if is_easter
            else "保持专业且清晰，尽量直达结论。"
        )
        return _chat(
            f"你是{expert.name}，职位：{expert.title}；专长：{expert.expertise}；"
            f"背景：{expert.background}；思维倾向：{expert.mindset}",
            f"讨论主题：{query}\n\n上下文：\n{context}\n\n表达风格要求：{style_hint}\n\n{instruction}",
            model_specialist,
            max_tokens=700,
        )

    rounds: list[dict] = []
    round_context = f"目标澄清:\n{objective}\n"

    if on_stage:
        on_stage("round_1", "第一回合：专家初步立场与核心判断。")
    speeches_1 = []
    for expert in experts:
        if should_stop and should_stop():
            raise RuntimeError("任务已被用户停止")
        content = round_speech(1, expert, round_context)
        speeches_1.append({"expert": expert.name, "content": content})
        if on_transcript:
            on_transcript(f"【第1轮】{expert.name}：{content[:220]}")
    rounds.append({"round": "1", "theme": "初步立场与核心判断", "speeches": speeches_1})

    if on_stage:
        on_stage("round_2", "第二回合：交叉质询与分歧碰撞。")
    round_context_2 = round_context + "\n\n".join([f"{s['expert']}:\n{s['content']}" for s in speeches_1])
    speeches_2 = []
    for expert in experts:
        if should_stop and should_stop():
            raise RuntimeError("任务已被用户停止")
        content = round_speech(2, expert, round_context_2)
        speeches_2.append({"expert": expert.name, "content": content})
        target, point = _extract_reference(content)
        interaction_timeline.append(
            {
                "round": "2",
                "from": expert.name,
                "to": target,
                "point": point,
            }
        )
        if on_transcript:
            on_transcript(f"【第2轮】{expert.name}回应{target}：{content[:220]}")
    rounds.append({"round": "2", "theme": "交叉质询与深度碰撞", "speeches": speeches_2})

    if on_stage:
        on_stage("round_3", "第三回合：综合判断与行动建议。")
    round_context_3 = round_context_2 + "\n\n".join([f"{s['expert']}:\n{s['content']}" for s in speeches_2])
    speeches_3 = []
    for expert in experts:
        if should_stop and should_stop():
            raise RuntimeError("任务已被用户停止")
        content = round_speech(3, expert, round_context_3)
        speeches_3.append({"expert": expert.name, "content": content})
        target, point = _extract_reference(content)
        interaction_timeline.append(
            {
                "round": "3",
                "from": expert.name,
                "to": target,
                "point": point,
            }
        )
        if on_transcript:
            on_transcript(f"【第3轮】{expert.name}综合判断：{content[:220]}")
    rounds.append({"round": "3", "theme": "综合与建议", "speeches": speeches_3})

    if on_stage:
        on_stage("deep_focus", "提炼关键分歧与深度聚焦议题。")
    disagreement_and_focus = _chat(
        "你是专家会议纪要助手。",
        (
            f"主题：{query}\n\n"
            f"回合内容：\n{json.dumps(rounds, ensure_ascii=False)}\n\n"
            "请输出两部分：\n"
            "1) ⚔️ 分歧焦点（2-3个）\n"
            "2) 🔍 深度聚焦模块（2个），每个模块包含【背景】【多方视角】【证据与数据】【综合判断】【行动含义】"
        ),
        model_judge,
        max_tokens=1400,
    )
    if on_transcript:
        on_transcript("【系统】已生成关键分歧与深度聚焦摘要。")

    if on_stage:
        on_stage("final_report", "生成专家组综合分析报告。")
    final_report = _chat(
        "你是专家组秘书长，负责输出结构化最终报告。",
        (
            f"分析主题：{query}\n"
            f"目标澄清：\n{objective}\n\n"
            f"专家列表：\n{json.dumps([asdict(e) for e in experts], ensure_ascii=False)}\n\n"
            f"三轮讨论：\n{json.dumps(rounds, ensure_ascii=False)}\n\n"
            f"互动时间线：\n{json.dumps(interaction_timeline, ensure_ascii=False)}\n\n"
            f"分歧与深度聚焦：\n{disagreement_and_focus}\n\n"
            "请严格按以下结构输出：\n"
            "专家组综合分析报告\n"
            "一、核心结论（专家共识）\n"
            "二、主要争议与分歧\n"
            "三、综合建议（按优先级）\n"
            "四、关键风险与注意事项\n"
            "五、下一步行动建议（可执行清单）"
        ),
        model_judge,
        max_tokens=1800,
    )
    if on_transcript:
        on_transcript("【系统】最终综合报告已生成。")

    return {
        "mode": "expert_panel",
        "objective": objective,
        "experts": [asdict(e) for e in experts],
        "rounds": rounds,
        "deep_focus": disagreement_and_focus,
        "final_report": final_report,
        "interaction_timeline": interaction_timeline,
    }
