import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.prompt_context import compact_history, compact_text, format_memories
logger = get_logger("default")


def create_research_manager(llm, memory):
    def research_manager_node(state) -> dict:
        history = state["investment_debate_state"].get("history", "")
        market_research_report = state["market_report"]
        a_share_sentiment_report = state.get("a_share_sentiment_report", "")
        fund_flow_report = state.get("fund_flow_report", "")
        theme_rotation_report = state.get("theme_rotation_report", "")
        institutional_theme_report = state.get("institutional_theme_report", "")
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        investment_debate_state = state["investment_debate_state"]

        market_research_report = compact_text(market_research_report, 1800, "research_manager.market_report")
        a_share_sentiment_report = compact_text(a_share_sentiment_report, 1200, "research_manager.a_share_sentiment")
        fund_flow_report = compact_text(fund_flow_report, 1200, "research_manager.fund_flow")
        theme_rotation_report = compact_text(theme_rotation_report, 1200, "research_manager.theme_rotation")
        institutional_theme_report = compact_text(institutional_theme_report, 1200, "research_manager.institutional_theme")
        sentiment_report = compact_text(sentiment_report, 800, "research_manager.sentiment")
        news_report = compact_text(news_report, 1000, "research_manager.news")
        fundamentals_report = compact_text(fundamentals_report, 1400, "research_manager.fundamentals")
        history = compact_history(history, 1400, "research_manager.history")

        curr_situation = f"{market_research_report}\n\n{a_share_sentiment_report}\n\n{fund_flow_report}\n\n{theme_rotation_report}\n\n{institutional_theme_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"

        # 安全检查：确保memory不为None
        if memory is not None:
            past_memories = memory.get_memories(curr_situation, n_matches=2)
        else:
            logger.warning(f"⚠️ [DEBUG] memory为None，跳过历史记忆检索")
            past_memories = []

        past_memory_str = format_memories(past_memories, max_chars=800, label="research_manager.memories")

        prompt = f"""作为投资组合经理和辩论主持人，您的职责是批判性地评估这轮辩论并做出明确决策：支持看跌分析师、看涨分析师，或者仅在基于所提出论点有强有力理由时选择持有。

简洁地总结双方的关键观点，重点关注最有说服力的证据或推理。您的建议——买入、卖出或持有——必须明确且可操作。避免仅仅因为双方都有有效观点就默认选择持有；要基于辩论中最强有力的论点做出承诺。

此外，为交易员制定详细的投资计划。这应该包括：

您的建议：基于最有说服力论点的明确立场。
理由：解释为什么这些论点导致您的结论。
战略行动：实施建议的具体步骤。
📊 目标价格分析：基于所有可用报告（基本面、新闻、情绪），提供全面的目标价格区间和具体价格目标。考虑：
- 基本面报告中的基本估值
- 新闻对价格预期的影响
- 情绪驱动的价格调整
- 技术支撑/阻力位
- 风险调整价格情景（保守、基准、乐观）
- 价格目标的时间范围（1个月、3个月、6个月）
💰 您必须提供具体的目标价格 - 不要回复"无法确定"或"需要更多信息"。

考虑您在类似情况下的过去错误。利用这些见解来完善您的决策制定，确保您在学习和改进。以对话方式呈现您的分析，就像自然说话一样，不使用特殊格式。

以下是您对错误的过去反思：
\"{past_memory_str}\"

以下是综合分析报告：
市场研究：{market_research_report}

A股盘面情绪：{a_share_sentiment_report}

A股资金面：{fund_flow_report}

A股题材轮动：{theme_rotation_report}

机构布局题材：{institutional_theme_report}

情绪分析：{sentiment_report}

新闻分析：{news_report}

基本面分析：{fundamentals_report}

以下是辩论：
辩论历史：
{history}

输出要求：
- 先给明确建议：买入/卖出/持有
- 然后用 3-5 条最关键理由说明
- 目标价只保留核心区间和一个基准目标价
- 避免重复转述辩论内容
- 总长度控制在 900 字以内

请用中文撰写所有分析内容和建议。"""

        # 📊 统计 prompt 大小
        prompt_length = len(prompt)
        estimated_tokens = int(prompt_length / 1.8)

        logger.info(f"📊 [Research Manager] Prompt 统计:")
        logger.info(f"   - 辩论历史长度: {len(history)} 字符")
        logger.info(f"   - 总 Prompt 长度: {prompt_length} 字符")
        logger.info(f"   - 估算输入 Token: ~{estimated_tokens} tokens")

        # ⏱️ 记录开始时间
        start_time = time.time()

        response = llm.bind(max_tokens=1100).invoke(prompt)

        # ⏱️ 记录结束时间
        elapsed_time = time.time() - start_time

        # 📊 统计响应信息
        response_length = len(response.content) if response and hasattr(response, 'content') else 0
        estimated_output_tokens = int(response_length / 1.8)

        logger.info(f"⏱️ [Research Manager] LLM调用耗时: {elapsed_time:.2f}秒")
        logger.info(f"📊 [Research Manager] 响应统计: {response_length} 字符, 估算~{estimated_output_tokens} tokens")

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node
