import time
import json

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.prompt_context import compact_history, compact_text
logger = get_logger("default")


def create_risky_debator(llm):
    def risky_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        risky_history = risk_debate_state.get("risky_history", "")

        current_safe_response = risk_debate_state.get("current_safe_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        a_share_sentiment_report = state.get("a_share_sentiment_report", "")
        fund_flow_report = state.get("fund_flow_report", "")
        theme_rotation_report = state.get("theme_rotation_report", "")
        institutional_theme_report = state.get("institutional_theme_report", "")
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        market_research_report = compact_text(market_research_report, 1400, "risky.market_report")
        a_share_sentiment_report = compact_text(a_share_sentiment_report, 900, "risky.a_share_sentiment")
        fund_flow_report = compact_text(fund_flow_report, 900, "risky.fund_flow")
        theme_rotation_report = compact_text(theme_rotation_report, 900, "risky.theme_rotation")
        institutional_theme_report = compact_text(institutional_theme_report, 900, "risky.institutional_theme")
        sentiment_report = compact_text(sentiment_report, 600, "risky.sentiment")
        news_report = compact_text(news_report, 800, "risky.news")
        fundamentals_report = compact_text(fundamentals_report, 1000, "risky.fundamentals")
        trader_decision = compact_text(trader_decision, 1000, "risky.trader_decision")
        history = compact_history(history, 1000, "risky.history")
        current_safe_response = compact_text(current_safe_response, 700, "risky.current_safe")
        current_neutral_response = compact_text(current_neutral_response, 700, "risky.current_neutral")

        # 📊 记录输入数据长度
        logger.info(f"📊 [Risky Analyst] 输入数据长度统计:")
        logger.info(f"  - market_report: {len(market_research_report):,} 字符")
        logger.info(f"  - a_share_sentiment_report: {len(a_share_sentiment_report):,} 字符")
        logger.info(f"  - fund_flow_report: {len(fund_flow_report):,} 字符")
        logger.info(f"  - theme_rotation_report: {len(theme_rotation_report):,} 字符")
        logger.info(f"  - institutional_theme_report: {len(institutional_theme_report):,} 字符")
        logger.info(f"  - sentiment_report: {len(sentiment_report):,} 字符")
        logger.info(f"  - news_report: {len(news_report):,} 字符")
        logger.info(f"  - fundamentals_report: {len(fundamentals_report):,} 字符")
        logger.info(f"  - trader_decision: {len(trader_decision):,} 字符")
        logger.info(f"  - history: {len(history):,} 字符")
        total_length = (len(market_research_report) + len(a_share_sentiment_report) + len(fund_flow_report) + len(theme_rotation_report) + len(institutional_theme_report) + len(sentiment_report) +
                       len(news_report) + len(fundamentals_report) +
                       len(trader_decision) + len(history) +
                       len(current_safe_response) + len(current_neutral_response))
        logger.info(f"  - 总Prompt长度: {total_length:,} 字符 (~{total_length//4:,} tokens)")

        prompt = f"""作为激进风险分析师，您的职责是积极倡导高回报、高风险的投资机会，强调大胆策略和竞争优势。在评估交易员的决策或计划时，请重点关注潜在的上涨空间、增长潜力和创新收益——即使这些伴随着较高的风险。使用提供的市场数据和情绪分析来加强您的论点，并挑战对立观点。具体来说，请直接回应保守和中性分析师提出的每个观点，用数据驱动的反驳和有说服力的推理进行反击。突出他们的谨慎态度可能错过的关键机会，或者他们的假设可能过于保守的地方。以下是交易员的决策：

{trader_decision}

您的任务是通过质疑和批评保守和中性立场来为交易员的决策创建一个令人信服的案例，证明为什么您的高回报视角提供了最佳的前进道路。将以下来源的见解纳入您的论点：

市场研究报告：{market_research_report}
A股盘面情绪报告：{a_share_sentiment_report}
A股资金面报告：{fund_flow_report}
A股题材轮动报告：{theme_rotation_report}
机构布局题材报告：{institutional_theme_report}
社交媒体情绪报告：{sentiment_report}
最新世界事务报告：{news_report}
公司基本面报告：{fundamentals_report}
以下是当前对话历史：{history} 以下是保守分析师的最后论点：{current_safe_response} 以下是中性分析师的最后论点：{current_neutral_response}。如果其他观点没有回应，请不要虚构，只需提出您的观点。

积极参与，解决提出的任何具体担忧，反驳他们逻辑中的弱点，并断言承担风险的好处以超越市场常规。专注于辩论和说服，而不仅仅是呈现数据。挑战每个反驳点，强调为什么高风险方法是最优的。

输出要求：
- 只写最重要的 3 条进攻性观点
- 直接反驳，不要大段铺垫
- 总长度控制在 600 字以内
- 请用中文输出"""

        logger.info(f"⏱️ [Risky Analyst] 开始调用LLM...")
        import time
        llm_start_time = time.time()

        response = llm.bind(max_tokens=800).invoke(prompt)

        llm_elapsed = time.time() - llm_start_time
        logger.info(f"⏱️ [Risky Analyst] LLM调用完成，耗时: {llm_elapsed:.2f}秒")

        argument = f"Risky Analyst: {response.content}"

        new_count = risk_debate_state["count"] + 1
        logger.info(f"🔥 [激进风险分析师] 发言完成，计数: {risk_debate_state['count']} -> {new_count}")

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "risky_history": risky_history + "\n" + argument,
            "safe_history": risk_debate_state.get("safe_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Risky",
            "current_risky_response": argument,
            "current_safe_response": risk_debate_state.get("current_safe_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": new_count,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return risky_node
