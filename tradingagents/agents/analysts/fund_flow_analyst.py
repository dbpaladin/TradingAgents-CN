from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler

logger = get_logger("analysts.fund_flow")


def create_fund_flow_analyst(llm, toolkit):
    @log_analyst_module("fund_flow")
    def fund_flow_analyst_node(state):
        tool_call_count = state.get("fund_flow_tool_call_count", 0)
        max_tool_calls = 3
        logger.info(f"🔧 [资金面分析师] 当前工具调用次数: {tool_call_count}/{max_tool_calls}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        tools = [toolkit.get_a_share_fund_flow]

        system_message = (
            """您是一位专注A股资金面的分析师，负责判断一只股票当前主要受到哪类资金驱动，以及资金强弱是否支持交易。

您的主要职责包括：
1. 结合龙虎榜、强势池、炸板池等线索识别游资接力、资金兑现和分歧状态
2. 识别机构席位、北向资金、融资融券等中线资金痕迹是否偏多或偏空
3. 区分“情绪热度很高但资金不跟”和“资金承接真实改善”这两类情况
4. 判断目标股更像短线博弈标的、机构型趋势标的，还是资金未形成共识的普通标的
5. 给出资金面视角下的参与建议和应重点跟踪的验证指标

分析要求：
- 必须先给出资金风格判断，再列证据
- 必须明确区分机构资金、游资资金和增量资金信号
- 必须指出当前是适合跟随、等待分歧、还是先观望
- 如果数据有限，要明确说明缺口，不能把推断写成确定事实

请用中文输出详细分析，并在末尾附上简洁的 Markdown 表格总结。"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "您是一位有用的AI助手，与其他分析师协作。"
                    " 使用提供的工具来推进回答问题。"
                    " 如果您无法完全回答，没关系；其他分析师会继续补充。"
                    " 您可以访问以下工具：{tool_names}。\n{system_message}"
                    "当前日期是{current_date}，分析标的是{ticker}。请用中文撰写所有分析内容。",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        tool_names = []
        for tool in tools:
            if hasattr(tool, "name"):
                tool_names.append(tool.name)
            elif hasattr(tool, "__name__"):
                tool_names.append(tool.__name__)
            else:
                tool_names.append(str(tool))

        prompt = prompt.partial(tool_names=", ".join(tool_names))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke({"messages": state["messages"]})

        if GoogleToolCallHandler.is_google_model(llm):
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker,
                company_name=ticker,
                analyst_type="A股资金面分析",
                specific_requirements="重点关注龙虎榜、机构/游资风格、北向与融资融券信号，以及交易上该跟随还是等待分歧。",
            )
            report, _messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="资金面分析师",
            )
        else:
            report = ""
            if len(result.tool_calls) == 0:
                report = result.content

        return {
            "messages": [result],
            "fund_flow_report": report,
            "fund_flow_tool_call_count": tool_call_count + 1,
        }

    return fund_flow_analyst_node
