# TradingAgents/graph/setup.py

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.agent_utils import Toolkit

from .conditional_logic import ConditionalLogic

# 导入统一日志系统
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        toolkit: Toolkit,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        risk_manager_memory,
        conditional_logic: ConditionalLogic,
        config: Dict[str, Any] = None,
        react_llm = None,
    ):
        """Initialize with required components."""
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.toolkit = toolkit
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.conditional_logic = conditional_logic
        self.config = config or {}
        self.react_llm = react_llm

    def setup_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include. Options are:
                - "market": Market analyst
                - "emotion": A-share sentiment analyst
                - "fund_flow": A-share fund flow analyst
                - "theme_rotation": A-share theme rotation analyst
                - "institutional_theme": Institutional theme analyst
                - "social": Social media analyst
                - "news": News analyst
                - "fundamentals": Fundamentals analyst
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # Create analyst nodes
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            # 现在所有LLM都使用标准市场分析师（包括阿里百炼的OpenAI兼容适配器）
            llm_provider = self.config.get("llm_provider", "").lower()

            # 检查是否使用OpenAI兼容的阿里百炼适配器
            using_dashscope_openai = (
                "dashscope" in llm_provider and
                hasattr(self.quick_thinking_llm, '__class__') and
                'OpenAI' in self.quick_thinking_llm.__class__.__name__
            )

            if using_dashscope_openai:
                logger.debug(f"📈 [DEBUG] 使用标准市场分析师（阿里百炼OpenAI兼容模式）")
            elif "dashscope" in llm_provider or "阿里百炼" in self.config.get("llm_provider", ""):
                logger.debug(f"📈 [DEBUG] 使用标准市场分析师（阿里百炼原生模式）")
            elif "deepseek" in llm_provider:
                logger.debug(f"📈 [DEBUG] 使用标准市场分析师（DeepSeek）")
            else:
                logger.debug(f"📈 [DEBUG] 使用标准市场分析师")

            # 所有LLM都使用标准分析师
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "emotion" in selected_analysts:
            analyst_nodes["emotion"] = create_a_share_sentiment_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["emotion"] = create_msg_delete()
            tool_nodes["emotion"] = self.tool_nodes["emotion"]

        if "fund_flow" in selected_analysts:
            analyst_nodes["fund_flow"] = create_fund_flow_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["fund_flow"] = create_msg_delete()
            tool_nodes["fund_flow"] = self.tool_nodes["fund_flow"]

        if "theme_rotation" in selected_analysts:
            analyst_nodes["theme_rotation"] = create_theme_rotation_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["theme_rotation"] = create_msg_delete()
            tool_nodes["theme_rotation"] = self.tool_nodes["theme_rotation"]

        if "institutional_theme" in selected_analysts:
            analyst_nodes["institutional_theme"] = create_institutional_theme_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["institutional_theme"] = create_msg_delete()
            tool_nodes["institutional_theme"] = self.tool_nodes["institutional_theme"]

        if "news" in selected_analysts:
            def _build_news_clear_state(state):
                news_report = state.get("news_report", "")
                if isinstance(news_report, str) and news_report.strip():
                    return {}

                ticker = state.get("company_of_interest", "未知股票")
                company_name = ticker
                reason = "新闻分析流程达到工具调用上限或未生成有效正文，已自动降级为占位报告。"
                degraded_report = (
                    f"## {ticker} 新闻分析降级报告\n\n"
                    f"- 分析对象：{company_name}（{ticker}）\n"
                    f"- 问题：{reason}\n"
                    f"- 处理建议：复查新闻工具返回、模型工具调用日志与 ToolMessage 汇总链路。\n"
                    f"- 结论：本次新闻维度结果无效，不应作为最终投资决策的强证据。\n"
                )
                return {"news_report": degraded_report}

            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["news"] = create_msg_delete(state_update_factory=_build_news_clear_state)
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            # 现在所有LLM都使用标准基本面分析师（包括阿里百炼的OpenAI兼容适配器）
            llm_provider = self.config.get("llm_provider", "").lower()

            # 检查是否使用OpenAI兼容的阿里百炼适配器
            using_dashscope_openai = (
                "dashscope" in llm_provider and
                hasattr(self.quick_thinking_llm, '__class__') and
                'OpenAI' in self.quick_thinking_llm.__class__.__name__
            )

            if using_dashscope_openai:
                logger.debug(f"📊 [DEBUG] 使用标准基本面分析师（阿里百炼OpenAI兼容模式）")
            elif "dashscope" in llm_provider or "阿里百炼" in self.config.get("llm_provider", ""):
                logger.debug(f"📊 [DEBUG] 使用标准基本面分析师（阿里百炼原生模式）")
            elif "deepseek" in llm_provider:
                logger.debug(f"📊 [DEBUG] 使用标准基本面分析师（DeepSeek）")
            else:
                logger.debug(f"📊 [DEBUG] 使用标准基本面分析师")

            # 所有LLM都使用标准分析师（包含强制工具调用机制）
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        # Create researcher and manager nodes
        bull_researcher_node = create_bull_researcher(
            self.quick_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.quick_thinking_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        # Create risk analysis nodes
        risky_analyst = create_risky_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        safe_analyst = create_safe_debator(self.quick_thinking_llm)
        risk_manager_node = create_risk_manager(
            self.deep_thinking_llm, self.risk_manager_memory
        )

        # Create workflow
        workflow = StateGraph(AgentState)

        # Add analyst nodes to the graph
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # Add other nodes
        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Risky Analyst", risky_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Safe Analyst", safe_analyst)
        workflow.add_node("Risk Judge", risk_manager_node)

        # Define edges
        # 单股/正式分析保持串行执行。分析师共用 messages 状态，
        # 并行时会混入彼此的 tool-call 历史，导致后续 LLM 请求报
        # "No tool output found for function call ..."。
        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i + 1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

        # Add remaining edges
        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Risky Analyst")
        workflow.add_conditional_edges(
            "Risky Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Safe Analyst": "Safe Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Safe Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Risky Analyst": "Risky Analyst",
                "Risk Judge": "Risk Judge",
            },
        )

        workflow.add_edge("Risk Judge", END)

        # Compile and return
        return workflow.compile()

    def setup_backtest_graph(
        self, selected_analysts=["market", "social", "news", "fundamentals"]
    ):
        """P1 优化：回测专用轻量图

        分析师并行 → 单次 LLM 综合决策（跳过 Bull/Bear 辩论 + 风险三方讨论）
        适用于回测场景：只需 BUY/SELL/HOLD 方向信号，不需要完整的多轮讨论。
        预计减少 ~8 次 LLM 调用 / 天。
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        # ---- 复用 setup_graph 的分析师节点创建逻辑 ----
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        analyst_creators = {
            "market": lambda: create_market_analyst(self.quick_thinking_llm, self.toolkit),
            "social": lambda: create_social_media_analyst(self.quick_thinking_llm, self.toolkit),
            "emotion": lambda: create_a_share_sentiment_analyst(self.quick_thinking_llm, self.toolkit),
            "fund_flow": lambda: create_fund_flow_analyst(self.quick_thinking_llm, self.toolkit),
            "theme_rotation": lambda: create_theme_rotation_analyst(self.quick_thinking_llm, self.toolkit),
            "institutional_theme": lambda: create_institutional_theme_analyst(self.quick_thinking_llm, self.toolkit),
            "news": lambda: create_news_analyst(self.quick_thinking_llm, self.toolkit),
            "fundamentals": lambda: create_fundamentals_analyst(self.quick_thinking_llm, self.toolkit),
        }

        for analyst_type in selected_analysts:
            if analyst_type in analyst_creators:
                analyst_nodes[analyst_type] = analyst_creators[analyst_type]()
                delete_nodes[analyst_type] = create_msg_delete(parallel_safe=True)
                tool_nodes[analyst_type] = self.tool_nodes[analyst_type]

        # 创建工作流
        workflow = StateGraph(AgentState)

        # 添加分析师节点
        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        # 添加回测决策节点
        backtest_decision_node = self._create_backtest_decision_node()
        workflow.add_node("Backtest Decision", backtest_decision_node)

        # 定义边：分析师并行执行 → 汇入决策节点
        for analyst_type in selected_analysts:
            if analyst_type not in analyst_nodes:
                continue
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            workflow.add_edge(START, current_analyst)
            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)
            workflow.add_edge(current_clear, "Backtest Decision")

        workflow.add_edge("Backtest Decision", END)

        logger.info(
            "🚀 [回测轻量图] 已构建: 分析师=%s → Backtest Decision → END (跳过辩论+风控)",
            list(analyst_nodes.keys()),
        )
        return workflow.compile()

    def _create_backtest_decision_node(self):
        """创建回测决策节点的工厂方法

        该节点综合所有分析师报告，通过单次 LLM 调用直接输出 BUY/SELL/HOLD 决策。
        替代完整流程中的 Bull/Bear 辩论 + Research Manager + Trader + 风险三方讨论 + Risk Judge。
        """
        llm = self.quick_thinking_llm

        def backtest_decision(state: AgentState):
            """回测轻量决策：综合分析师报告 → 直接输出交易信号"""
            import time as _time
            start_time = _time.time()

            company = state.get("company_of_interest", "未知")
            trade_date = state.get("trade_date", "未知")

            # 收集所有分析师报告（截断以控制 token）
            report_keys = [
                ("市场分析", "market_report"),
                ("基本面", "fundamentals_report"),
                ("新闻", "news_report"),
                ("社交舆情", "sentiment_report"),
                ("A股情绪", "a_share_sentiment_report"),
                ("资金流向", "fund_flow_report"),
                ("题材轮动", "theme_rotation_report"),
                ("机构布局", "institutional_theme_report"),
            ]

            reports_text = []
            for label, key in report_keys:
                content = state.get(key, "")
                if content and len(content.strip()) > 10:
                    # 截断到 400 字符以控制总 token 量
                    truncated = content.strip()[:400]
                    reports_text.append(f"【{label}】\n{truncated}")

            if not reports_text:
                logger.warning(f"⚠️ [回测决策] {company} {trade_date} 无分析师报告，默认 HOLD")
                return {
                    "final_trade_decision": "HOLD - 无分析师报告可用",
                    "investment_plan": "无数据，建议持有观望",
                    "trader_investment_plan": "HOLD",
                    "investment_debate_state": {
                        "bull_history": "", "bear_history": "", "history": "",
                        "current_response": "Backtest Decision", "judge_decision": "HOLD",
                        "count": 0,
                    },
                    "risk_debate_state": {
                        "risky_history": "", "safe_history": "", "neutral_history": "",
                        "history": "", "latest_speaker": "Backtest Decision",
                        "current_risky_response": "", "current_safe_response": "",
                        "current_neutral_response": "", "judge_decision": "HOLD",
                        "count": 0,
                    },
                }

            combined_reports = "\n---\n".join(reports_text)

            prompt = f"""你是一位专业的A股交易决策助手。根据以下分析师报告，为 {company} 在 {trade_date} 做出交易决策。

{combined_reports}

请直接给出交易建议，格式要求：
1. 第一行必须是: BUY 或 SELL 或 HOLD
2. 第二行给出简要理由（不超过100字）
3. 第三行给出置信度（0-1之间的数字）

只输出以上3行，不要附加其他内容。"""

            try:
                response = llm.invoke(prompt)
                decision_text = response.content.strip() if hasattr(response, 'content') else str(response).strip()
                logger.info(f"✅ [回测决策] {company} {trade_date}: {decision_text[:80]}...")
            except Exception as e:
                logger.error(f"❌ [回测决策] LLM 调用失败: {e}")
                decision_text = "HOLD\nLLM调用失败，默认持有\n0.3"

            elapsed = _time.time() - start_time
            logger.info(f"⏱️ [Backtest Decision] 耗时: {elapsed:.2f}秒")

            return {
                "final_trade_decision": decision_text,
                "investment_plan": f"回测快速决策: {decision_text[:200]}",
                "trader_investment_plan": decision_text.split('\n')[0] if decision_text else "HOLD",
                "investment_debate_state": {
                    "bull_history": "", "bear_history": "",
                    "history": f"回测快速决策模式 - 跳过辩论",
                    "current_response": "Backtest Decision",
                    "judge_decision": decision_text.split('\n')[0] if decision_text else "HOLD",
                    "count": 0,
                },
                "risk_debate_state": {
                    "risky_history": "", "safe_history": "", "neutral_history": "",
                    "history": f"回测快速决策模式 - 跳过风控讨论",
                    "latest_speaker": "Backtest Decision",
                    "current_risky_response": "", "current_safe_response": "",
                    "current_neutral_response": "",
                    "judge_decision": decision_text.split('\n')[0] if decision_text else "HOLD",
                    "count": 0,
                },
            }

        return backtest_decision
