from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler

logger = get_logger("analysts.theme_rotation")


def create_theme_rotation_analyst(llm, toolkit):
    @log_analyst_module("theme_rotation")
    def theme_rotation_analyst_node(state):
        tool_call_count = state.get("theme_rotation_tool_call_count", 0)
        max_tool_calls = 3
        logger.info(f"🔧 [题材轮动分析师] 当前工具调用次数: {tool_call_count}/{max_tool_calls}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [toolkit.get_a_share_theme_rotation]

        system_message = (
            """您是一位专注中国A股题材热点、主线板块和轮动节奏的分析师。

您的主要职责包括：
1. 判断当前市场是否存在明确主线题材
2. 识别题材所处阶段：启动、发酵、强化、分歧、退潮
3. 区分龙头、前排核心、补涨跟风和边缘个股
4. 判断目标股是“题材逻辑”还是“独立逻辑”
5. 评估是否适合用题材交易框架来参与

分析要求：
- 必须明确写出当前主线题材与轮动信号
- 必须判断目标股在题材中的角色定位，并使用以下三档之一明确标注：主线核心、主线外延、非主线
- 如果目标股主营或业务链条与主线有关，但不是涨停前排或辨识度核心，必须写成“主线外延”或“主线相关但非核心”，禁止直接写成“无主线关联”
- 必须指出适合的交易动作：围绕主线、只低吸不追高、观察等待、避免参与
- 不要把题材热度与长期基本面混为一谈
- 如果当前主线不清晰，也要明确写出“主线不清晰”
- 若引用评分，必须解释评分含义，例如：80分以上=主线核心，50-79分=主线外延，50分以下=非主线或边缘标的
- 必须单独写一段“为什么不是核心”，避免只给结论不给依据

输出结构要求：
1. 当前主线与阶段
2. 目标股题材归属
3. 角色定位与评分解释
4. 交易适配性
5. 简洁表格总结

请输出详细的中文分析，并在末尾附上一个简洁的 Markdown 表格总结结论。"""
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
                analyst_type="A股题材轮动分析",
                specific_requirements="重点关注主线题材、题材阶段、目标股在题材中的角色和交易适配性。",
            )
            report, _messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result,
                llm=llm,
                tools=tools,
                state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="题材轮动分析师",
            )
        else:
            report = ""
            if len(result.tool_calls) == 0:
                report = result.content

        return {
            "messages": [result],
            "theme_rotation_report": report,
            "theme_rotation_tool_call_count": tool_call_count + 1,
        }

    return theme_rotation_analyst_node
