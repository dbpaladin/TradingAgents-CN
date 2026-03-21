from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler

logger = get_logger("analysts.a_share_sentiment")


def create_a_share_sentiment_analyst(llm, toolkit):
    @log_analyst_module("a_share_sentiment")
    def a_share_sentiment_analyst_node(state):
        tool_call_count = state.get("a_share_sentiment_tool_call_count", 0)
        max_tool_calls = 3
        logger.info(f"🔧 [A股情绪分析师] 当前工具调用次数: {tool_call_count}/{max_tool_calls}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [toolkit.get_a_share_market_sentiment]

        system_message = (
            """您是一位专注A股短线盘面情绪的分析师，负责判断市场当前所处的情绪周期，并识别龙头、梯队和亏钱效应。

您的主要职责包括：
1. 识别市场所处阶段：冰点、修复、发酵、高潮、分化、退潮
2. 分析涨停家数、跌停家数、炸板率、连板高度、昨日涨停晋级率
3. 识别主线板块、前排龙头、跟风杂毛和亏钱效应
4. 评估龙虎榜活跃度、封板质量和高位股承接
5. 给出适合当前周期的仓位和节奏建议

分析要求：
- 必须先分析“市场总情绪”，再分析“主线/板块情绪”，最后分析“个股情绪定位”
- 必须明确写出当前情绪周期和对应证据
- 必须区分“可参与方向”和“应规避方向”
- 必须指出当前更适合低吸、打板、半路、趋势跟随还是观望
- 必须结合个股在当前情绪生态中的地位进行判断

请用中文输出详细分析，并在末尾附上简洁的Markdown表格总结关键结论。"""
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "您是一位有用的AI助手，与其他助手协作。"
                    " 使用提供的工具来推进回答问题。"
                    " 如果您无法完全回答，没关系；其他助手会继续补充。"
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
                analyst_type="A股盘面情绪分析",
                specific_requirements="重点关注情绪周期、连板梯队、炸板反馈、龙头辨识度和仓位节奏。"
            )
            report, messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="A股情绪分析师"
            )
        else:
            report = ""
            if len(result.tool_calls) == 0:
                report = result.content

        return {
            "messages": [result],
            "a_share_sentiment_report": report,
            "a_share_sentiment_tool_call_count": tool_call_count + 1,
        }

    return a_share_sentiment_analyst_node
