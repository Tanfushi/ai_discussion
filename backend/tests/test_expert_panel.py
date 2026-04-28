from app.orchestrator.expert_panel import should_use_expert_panel, experts_by_keys


def test_keyword_trigger():
    assert should_use_expert_panel("请做一次专家讨论和深度分析")


def test_complex_goal_trigger():
    assert should_use_expert_panel("请全面评估这个技术架构方案的风险与权衡")


def test_non_trigger():
    assert not should_use_expert_panel("帮我写一句宣传文案")


def test_select_experts_by_keys():
    experts = experts_by_keys(["expert_1", "expert_2", "expert_999"])
    assert len(experts) == 2
